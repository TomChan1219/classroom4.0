from sqlmodel import SQLModel, create_engine, Session

# 1. 定义数据库文件名
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

# 2. 创建数据库引擎 (这里就是报错说找不到的 engine)
# check_same_thread=False 是 SQLite 在 FastAPI 中必须的配置
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

# 3. 创建表结构的函数
def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

# 4. 获取数据库会话的依赖函数
def get_session():
    with Session(engine) as session:
        yield session