# 👇 --- [PATCH START] 强制使用 IPv4 (解决 Render 连不上 Gmail 的绝招) ---
import socket
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return socket.getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4
# 👆 --- [PATCH END] ---

import os
from fastapi import FastAPI, Depends, Request, Form, Query, BackgroundTasks
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select, or_
from database import engine, create_db_and_tables, get_session
from models import Room, Booking, TimeSlot, BookingStatus, BookingType
from datetime import date, datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.header import Header

app = FastAPI()
templates = Jinja2Templates(directory="templates")
SEMESTER_START = date(2025, 9, 8)

# --- 📧 邮件配置 (Gmail版 + IPv4补丁 + 465端口) ---
SMTP_CONFIG = {
    "ENABLE": True,
    "SERVER": "smtp.gmail.com",
    "PORT": 465,  # 👈 改回 465 (SSL模式)
    "EMAIL": "chenxz1219@gmail.com",
    "PASSWORD": "gtuiqwuvjakypghq"  # 👈 你的应用专用密码
}

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
    
    print(f"📧 当前邮件开关状态: {SMTP_CONFIG['ENABLE']}")
    
    if not SMTP_CONFIG["ENABLE"] or "your_email" in SMTP_CONFIG["EMAIL"]:
        print("❌ 邮件功能已关闭或未配置，跳过发送")
        return

    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['From'] = SMTP_CONFIG["EMAIL"]
        msg['To'] = to_email
        msg['Subject'] = Header(subject, 'utf-8')
        
        print(f"1. [IPv4模式] 正在连接 Gmail (端口 {SMTP_CONFIG['PORT']})...")
        
        # ✅ 关键修改：使用 SMTP_SSL (465端口) + 30秒超时设置
        server = smtplib.SMTP_SSL(SMTP_CONFIG["SERVER"], SMTP_CONFIG["PORT"], timeout=30)
        
        print("2. 连接成功，正在登录...")
        server.login(SMTP_CONFIG["EMAIL"], SMTP_CONFIG["PASSWORD"])
        
        print("3. 登录成功，正在发送...")
        server.send_message(msg)
        server.quit()
        
        print("✅ 邮件发送成功！") 
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    with Session(engine) as session:
        if not session.exec(select(Room)).first():
            demo_rooms = [
                Room(name="综合实验室（信103）", capacity=60, features="白板、多媒体"),
                Room(name="ERP实验室（信402）", capacity=60, features="白板、多媒体"),
                Room(name="国际课程实验室（东A301）", capacity=60, features="白板、多媒体"),
                Room(name="互联网+新商科实验室（西A303）", capacity=80, features="白板、多媒体"),
                Room(name="法语视听室（西A305）", capacity=56, features="白板、多媒体"),
                Room(name="金融科技创新实验室（西A402）", capacity=90, features="白板、多媒体"),
                Room(name="大数据与商业智能实验室（西A403）", capacity=90, features="白板、多媒体"),
            ]
            session.add_all(demo_rooms)
            session.commit()

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
    
    pending_list = session.exec(select(Booking).where(Booking.status == BookingStatus.PENDING).order_by(Booking.created_at)).all()
    approved_list = session.exec(select(Booking).where(Booking.status == BookingStatus.APPROVED).order_by(Booking.booking_date.desc())).all()

    dashboard_rows = []
    slots_list = list(TimeSlot)
    
    for day_date in dates_in_week:
        week_num, weekday_cn = get_week_info(day_date)
        for slot in slots_list:
            row_data = {
                "week": f"第{week_num}周", "date": day_date, "weekday": weekday_cn,
                "is_sunday": (day_date.weekday() == 6), "slot": slot.value, "slot_enum": slot.name, "cells": []
            }
            for room in rooms:
                found = next((b for b in bookings if b.room_id == room.id and b.booking_date == day_date and b.slot == slot), None)
                status = "FREE"
                if row_data["is_sunday"]: status = "SUNDAY"
                elif found:
                    status = "COURSE" if found.booking_type == BookingType.COURSE else ("TAKEN" if found.status == BookingStatus.APPROVED else "PENDING")
                row_data["cells"].append({"room_id": room.id, "status": status, "booking": found})
            dashboard_rows.append(row_data)

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "rooms": rooms, "dashboard_rows": dashboard_rows,
        "pending_list": pending_list, "approved_list": approved_list,
        "current_week_start": start_of_week, "prev_week": start_of_week - timedelta(days=7),
        "next_week": start_of_week + timedelta(days=7), "msg": msg, "slots_list": slots_list
    })

@app.post("/api/validate_password")
def validate_password(password: str = Form(...)):
    # 这里也可以改成从环境变量读取密码，更安全
    admin_pwd = os.getenv("ADMIN_PASSWORD", "123456")
    if password == admin_pwd:
        return {"valid": True}
    else:
        return {"valid": False}

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
