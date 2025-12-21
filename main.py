from fastapi import FastAPI, Depends, Request, Form, Query, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from sqlmodel import Session, select, or_
from database import engine, create_db_and_tables, get_session
from models import Room, Booking, TimeSlot, BookingStatus, BookingType
from datetime import date, datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# ✅ 引入大模型相关库
from openai import OpenAI
from pydantic import BaseModel

# ✅ 外部API(天气) + 统计图表数据接口 需要的最小依赖
import json
import time
import ssl
import urllib.request
import urllib.parse
from typing import Any, Dict, List

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ✅ 避免 Jinja 里 date/datetime undefined
templates.env.globals["date"] = date
templates.env.globals["datetime"] = datetime

SEMESTER_START = date(2025, 9, 8)

# --- 📧 邮件配置 ---
SMTP_CONFIG = {
    "ENABLE": True,
    "SERVER": "smtp.163.com",
    "PORT": 465,
    "EMAIL": "13925548126@163.com",
    "PASSWORD": "NJuBf6xSk2YdKTQH"
}

# --- 🤖 LLM (DeepSeek) 配置 ---
# 请妥善保管 API Key，不要上传到公开代码仓库
DEEPSEEK_API_KEY = "sk-de4250b259084b839fa47d2570895f3e"
LLM_CLIENT = OpenAI(
    api_key=DEEPSEEK_API_KEY, 
    base_url="https://api.deepseek.com"
)

# --- 🏫 详细的课室数据源 (用于初始化数据库) ---
ROOM_DATA_SOURCE = [
    {
        "name": "ERP实验室（信402）",
        "capacity": 70,
        "features": "ERP财务管理创新实验室面积约130平方米，可满足约70名学生的实验教学，支持分组实验的教学模式。按照8个小组、每组8-9人的配置安排实验机位。实验室有配套的ERP电子沙盘及物理沙盘设备，满足竞赛及教学需求。"
    },
    {
        "name": "互联网+新商科实验室（西A303）",
        "capacity": 80,
        "features": "互联网+新商科实验室共有80个智能工位，每个位置都配备翻盖桌电脑，让空间灵活适应多样化的实验场景。互联网+新商科实验室充分利用虚拟仿真技术，并依托区块链金融实验平台和财务大数据实验平台，促进人才培养紧跟数字经济的发展趋势，为学院培养具有数据思维、创新意识和学科协同的复合型新商科人才提供有力支持。"
    },
    {
        "name": "国际课程实验室（东A301）",
        "capacity": 60,
        "features": "国际课程实验室设施齐全，是全能型的教学空间，配备60套可移动的组合桌椅，可自由组合，按需排列，配合不同的使用场景以及教学模式。其两点在于课室配备了纳米工艺投影书写一体墙，实现一墙两用。"
    },
    {
        "name": "大数据与商业智能实验室（西A403）",
        "capacity": 90,
        "features": "大数据与商业智能实验室，是一个集科学研究、技术创新与高层次人才培养于一体的综合性实验室。宽敞空间布局合理，90套桌椅井然有序。这里是洞察市场趋势、挖掘商业价值的智慧殿堂，同样适合大规模教学与使用。"
    },
    {
        "name": "法语视听室（西A305）",
        "capacity": 40,
        "features": "法语视听说及口译实验室，配备40套一体化学生电脑桌，灵活桌椅设计激发无限布局创意。教室四周配备四块高清显示屏，确保每位师生无死角沉浸学习视界。内置智能课程管理系统，教师轻松掌握学情，学生便捷提问互动，共筑活跃和谐课堂新生态。"
    },
    {
        "name": "综合实验室（信103）",
        "capacity": 72,
        "features": "国际化综合实验室，配备72套高速学生电脑，预装用友财务、企业电子沙盘、土地数据库、CREIS房地产数据系统、国泰安数据库、SAS及维新房地产营销教学软件等财务金融房地产专业软件，助力财务管理与金融学实验实践课程。同时，配备语言学习系统及法语学习软件如Antidote，支持法语专业语言训练，集多功能于一体。"
    },
    {
        "name": "金融科技创新实验室（西A402）",
        "capacity": 90,
        "features": "金融科技创新实验室，配备了90套人体工学桌椅，空间宽敞，采光优良。智能教学设备助力多元化教学。灵活桌椅布局促进团队协作与独立研究，高速网络与先进软件让学生接轨市场前沿，适合大规模教学。"
    }
]


# =========================
# ✅ 外部 API：佛山天气（Open-Meteo，无需Key）
# =========================
_OPENMETEO_CTX = ssl.create_default_context()
_WEATHER_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_WEATHER_CACHE_SECONDS = 600  # 10分钟缓存


def _fetch_json(url: str, timeout: int = 6) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SCNU-IBC-SAC-BookingSystem/1.0 (Weather API)"}
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_OPENMETEO_CTX) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        return json.loads(raw)


def _resolve_city_latlon(city: str = "佛山") -> Dict[str, Any]:
    q = urllib.parse.quote(city)
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={q}&count=1&language=zh&format=json"
    data = _fetch_json(url)
    results = data.get("results") or []
    if not results:
        raise RuntimeError("geocoding_empty")
    r0 = results[0]
    return {
        "name": r0.get("name", city),
        "country": r0.get("country"),
        "admin1": r0.get("admin1"),
        "latitude": r0.get("latitude"),
        "longitude": r0.get("longitude"),
        "timezone": r0.get("timezone") or "Asia/Shanghai"
    }


@app.get("/api/weather")
def api_weather(city: str = Query(default="佛山")):
    now = time.time()
    if _WEATHER_CACHE["data"] and (now - _WEATHER_CACHE["ts"] < _WEATHER_CACHE_SECONDS):
        return JSONResponse({"ok": True, "cached": True, **_WEATHER_CACHE["data"]})

    try:
        geo = _resolve_city_latlon(city)
        lat, lon, tz = geo["latitude"], geo["longitude"], geo["timezone"]

        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current_weather=true&timezone={urllib.parse.quote(tz)}"
        )
        w = _fetch_json(url)
        cur = w.get("current_weather") or {}

        payload = {
            "city": geo.get("name", city),
            "region": f'{geo.get("admin1","") or ""} {geo.get("country","") or ""}'.strip(),
            "temp_c": cur.get("temperature"),
            "wind_kmh": cur.get("windspeed"),
            "code": cur.get("weathercode"),
            "time": cur.get("time"),
        }

        _WEATHER_CACHE["ts"] = now
        _WEATHER_CACHE["data"] = payload
        return JSONResponse({"ok": True, "cached": False, **payload})

    except Exception as e:
        return JSONResponse({
            "ok": False,
            "error": str(e) or "weather_fetch_failed",
            "city": city
        })


# =========================
# ✅ 图表数据接口
# =========================
@app.get("/api/stats/room_usage")
def api_room_usage(
    view_date: date = Query(default=date.today()),
    session: Session = Depends(get_session)
):
    start_of_week = view_date - timedelta(days=view_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    rooms = session.exec(select(Room).order_by(Room.name)).all()
    bookings = session.exec(select(Booking).where(
        Booking.booking_date >= start_of_week,
        Booking.booking_date <= end_of_week,
        Booking.status != BookingStatus.REJECTED
    )).all()

    counter: Dict[int, int] = {}
    for b in bookings:
        counter[b.room_id] = counter.get(b.room_id, 0) + 1

    labels = [r.name for r in rooms]
    values = [counter.get(r.id, 0) for r in rooms]

    return JSONResponse({
        "ok": True,
        "week_start": str(start_of_week),
        "week_end": str(end_of_week),
        "labels": labels,
        "values": values
    })


# =========================
# ✅ 新增：AI 问答接口 (RAG)
# =========================
class ChatRequest(BaseModel):
    message: str

@app.post("/api/chat")
def chat_with_ai(
    req: ChatRequest,
    session: Session = Depends(get_session)
):
    user_query = req.message
    
    # 1. 从数据库查出所有课室
    rooms = session.exec(select(Room)).all()
    
    # 2. 构建给 AI 看的“参考资料” (RAG Context)
    # 结合数据库里存的 features (详细描述)
    room_context_str = ""
    for i, r in enumerate(rooms, 1):
        room_context_str += f"{i}. 【{r.name}】 (容量:{r.capacity}人)\n   介绍: {r.features}\n\n"
    
    # 3. 系统提示词
    system_prompt = f"""
    你是SCNU IBC实创中心的智能课室助手，请根据以下【课室列表】回答用户的问题。
    
    === 课室列表开始 ===
    {room_context_str}
    === 课室列表结束 ===
    
    用户的当前问题是：{user_query}
    
    回答要求：
    1. 必须根据【课室列表】中的"介绍"和"容量"来推荐。
    2. 如果用户问"哪里有沙盘"，你要找描述里包含沙盘的课室。
    3. 如果用户问"适合小组讨论"，你要找支持分组或桌椅灵活的课室。
    4. 只有当用户询问天气时，你才可以说“请查看页面右上角的天气小组件”。
    5. 【重要】检测用户提问的语言。如果用户用英文提问，请务必用英文回答；如果用户用中文提问，请用中文回答。
    6. 回答要亲切、专业、简练。
    """
    
    try:
        response = LLM_CLIENT.chat.completions.create(
            model="deepseek-chat", 
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.5 
        )
        reply = response.choices[0].message.content
        return {"ok": True, "reply": reply}
        
    except Exception as e:
        print(f"AI Error: {e}")
        return {"ok": False, "reply": "抱歉，我的大脑暂时短路了，请检查后端日志或API Key设置。"}


# =========================
# 原有逻辑：周次/日期工具
# =========================
def get_week_info(target_date: date):
    delta_days = (target_date - SEMESTER_START).days
    week_num = (delta_days // 7) + 1
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][target_date.weekday()]
    return week_num, weekday_cn


def get_date_by_week_and_weekday(week_num: int, weekday_idx: int):
    days_to_add = (week_num - 1) * 7 + weekday_idx
    return SEMESTER_START + timedelta(days=days_to_add)


def send_email_task(to_email: str, subject: str, body: str):
    print(f"====== [模拟邮件发送] ======\n收件人: {to_email}\n标题: {subject}\n内容:\n{body}\n===========================")
    if not SMTP_CONFIG["ENABLE"] or "your_email" in SMTP_CONFIG["EMAIL"]:
        return
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = SMTP_CONFIG["EMAIL"]
        msg['To'] = to_email
        msg['Subject'] = Header(subject, 'utf-8')
        server = smtplib.SMTP_SSL(SMTP_CONFIG["SERVER"], SMTP_CONFIG["PORT"])
        server.login(SMTP_CONFIG["EMAIL"], SMTP_CONFIG["PASSWORD"])
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    with Session(engine) as session:
        # 如果数据库没有课室数据，则进行初始化
        if not session.exec(select(Room)).first():
            print("⏳ 正在初始化课室数据 (写入详细描述)...")
            demo_rooms = []
            for item in ROOM_DATA_SOURCE:
                r = Room(
                    name=item["name"], 
                    capacity=item["capacity"], 
                    features=item["features"]
                )
                demo_rooms.append(r)
            
            session.add_all(demo_rooms)
            session.commit()
            print("✅ 课室数据初始化完成！")


@app.get("/")
def dashboard(
    request: Request,
    view_date: date = Query(default=date.today()),
    msg: str = None,
    session: Session = Depends(get_session)
):
    start_of_week = view_date - timedelta(days=view_date.weekday())
    dates_in_week = [start_of_week + timedelta(days=i) for i in range(7)]

    rooms = session.exec(select(Room).order_by(Room.name)).all()
    bookings = session.exec(select(Booking).where(
        Booking.booking_date >= start_of_week,
        Booking.booking_date <= dates_in_week[-1],
        Booking.status != BookingStatus.REJECTED
    )).all()

    pending_list = session.exec(
        select(Booking).where(Booking.status == BookingStatus.PENDING).order_by(Booking.created_at)
    ).all()
    approved_list = session.exec(
        select(Booking).where(Booking.status == BookingStatus.APPROVED).order_by(Booking.booking_date.desc())
    ).all()

    dashboard_rows = []
    slots_list = list(TimeSlot)

    for day_date in dates_in_week:
        week_num, weekday_cn = get_week_info(day_date)
        for slot in slots_list:
            row_data = {
                "week": f"第{week_num}周",
                "date": day_date,
                "weekday": weekday_cn,
                "is_sunday": (day_date.weekday() == 6),
                "slot": slot.value,
                "slot_enum": slot.name,
                "cells": []
            }
            for room in rooms:
                found = next(
                    (b for b in bookings if b.room_id == room.id and b.booking_date == day_date and b.slot == slot),
                    None
                )
                status = "FREE"
                if row_data["is_sunday"]:
                    status = "SUNDAY"
                elif found:
                    status = "COURSE" if found.booking_type == BookingType.COURSE else (
                        "TAKEN" if found.status == BookingStatus.APPROVED else "PENDING"
                    )
                row_data["cells"].append({"room_id": room.id, "status": status, "booking": found})
            dashboard_rows.append(row_data)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "rooms": rooms,
        "dashboard_rows": dashboard_rows,
        "pending_list": pending_list,
        "approved_list": approved_list,
        "current_week_start": start_of_week,
        "prev_week": start_of_week - timedelta(days=7),
        "next_week": start_of_week + timedelta(days=7),
        "msg": msg,
        "slots_list": slots_list
    })


@app.post("/api/validate_password")
def validate_password(password: str = Form(...)):
    return {"valid": password == "123456"}


@app.post("/submit_booking")
async def submit_booking(
    request: Request,
    room_id: int = Form(...),
    booking_date: date = Form(...),
    student_id: str = Form(None), student_name: str = Form(None),
    student_email: str = Form(None), instructor_name: str = Form(None),
    purpose: str = Form(None),
    mode: str = Form("student"),
    start_week: int = Form(1), end_week: int = Form(1),
    session: Session = Depends(get_session)
):
    form_data = await request.form()
    selected_slots = form_data.getlist("slot")

    if mode == "course":
        course_name = form_data.get("course_name")
        course_teacher = form_data.get("course_teacher")
        target_weekday = booking_date.weekday()

        for week in range(start_week, end_week + 1):
            target_date = get_date_by_week_and_weekday(week, target_weekday)
            for slot_val in selected_slots:
                conflicts = session.exec(select(Booking).where(
                    Booking.room_id == room_id, Booking.booking_date == target_date,
                    Booking.slot == slot_val, Booking.status == BookingStatus.PENDING
                )).all()
                for c in conflicts:
                    c.status = BookingStatus.REJECTED
                    c.admin_comment = f"系统自动驳回：第{week}周课程优先占用"
                    session.add(c)

                new_booking = Booking(
                    student_id="ADMIN", student_name=course_name,
                    instructor_name=course_teacher,
                    room_id=room_id, booking_date=target_date, slot=slot_val,
                    purpose=f"第{week}周课程", status=BookingStatus.APPROVED, booking_type=BookingType.COURSE
                )
                session.add(new_booking)

        session.commit()
        return RedirectResponse(url="/?msg=course_added&role=admin", status_code=303)

    else:
        slot_val = selected_slots[0]
        conflict = session.exec(select(Booking).where(
            Booking.room_id == room_id, Booking.booking_date == booking_date, Booking.slot == slot_val,
            or_(Booking.status == BookingStatus.APPROVED, Booking.booking_type == BookingType.COURSE)
        )).first()
        if conflict:
            return RedirectResponse(url="/?msg=error_conflict&role=student", status_code=303)

        new_booking = Booking(
            student_id=student_id, student_name=student_name,
            student_email=student_email, instructor_name=instructor_name,
            room_id=room_id, booking_date=booking_date, slot=slot_val,
            purpose=purpose, status=BookingStatus.PENDING, booking_type=BookingType.STUDENT
        )
        session.add(new_booking)
        session.commit()
        return RedirectResponse(url="/?msg=submitted&role=student", status_code=303)


@app.post("/audit/{booking_id}")
def audit_booking(
    booking_id: int,
    action: str = Form(...),
    cancel_reason: str = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    session: Session = Depends(get_session)
):
    booking = session.get(Booking, booking_id)
    if not booking:
        return RedirectResponse(url="/?msg=error&role=admin", status_code=303)

    room_name = booking.room.name if booking.room else f"Room {booking.room_id}"
    email_target = booking.student_email

    should_send_email = (booking.booking_type == BookingType.STUDENT) and email_target

    if action == "approve":
        booking.status = BookingStatus.APPROVED

        conflicts = session.exec(select(Booking).where(
            Booking.room_id == booking.room_id, Booking.booking_date == booking.booking_date,
            Booking.slot == booking.slot, Booking.status == BookingStatus.PENDING, Booking.id != booking.id
        )).all()
        for c in conflicts:
            c.status = BookingStatus.REJECTED
            c.admin_comment = "系统自动驳回：已被其他优先申请占用"
            session.add(c)

        if should_send_email:
            subject = f"【预约成功】{booking.booking_date} {room_name} 预约已确认"
            content = f"""
亲爱的 {booking.student_name} 同学：

您好！您申请的课室预约已审核通过。

📅 日期：{booking.booking_date}
⏰ 时间：{booking.slot.value} 
🏫 地点：{room_name}
📝 用途：{booking.purpose}

【使用注意事项】
1. 离开时请整理桌椅，带走垃圾。
2. 请关闭电灯、空调及教学设备。
3. 课室仅限申请用途使用。

祝您学习愉快！
IBC实创中心助理
            """
            background_tasks.add_task(send_email_task, email_target, subject, content)

    elif action == "reject" or action == "delete":
        is_rejection = (action == "reject")

        booking.status = BookingStatus.REJECTED
        booking.admin_comment = cancel_reason

        if should_send_email:
            title_prefix = "申请驳回" if is_rejection else "预约取消"
            subject = f"【{title_prefix}通知】{booking.booking_date} {room_name}"
            reason_text = cancel_reason if cancel_reason else "管理员未填写具体原因"
            action_text = "的预约申请未能通过审核" if is_rejection else "的预约申请已被取消"

            content = f"""
亲爱的 {booking.student_name} 同学：

很抱歉地通知您，您在 {booking.booking_date} {booking.slot.value} 对 {room_name} {action_text}。

❌ 原因：{reason_text}

温馨提示：如果您还有预约需求，请尝试重新提交预约请求或预约其它课室。

如有疑问，请联系管理助理。
IBC实创中心助理
            """
            background_tasks.add_task(send_email_task, email_target, subject, content)
        else:
            print(f"✅ 课程/无邮箱记录已处理，未发送邮件。原因：{cancel_reason}")

    session.add(booking)
    session.commit()
    return RedirectResponse(url="/?msg=audit_done&role=admin", status_code=303)
