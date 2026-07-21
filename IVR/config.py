"""
系统配置管理
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # 阿里云
    ALIYUN_ACCESS_KEY_ID: str = ""
    ALIYUN_ACCESS_KEY_SECRET: str = ""
    ALIYUN_REGION_ID: str = "cn-shanghai"

    # CCC 云联络中心
    CCC_INSTANCE_ID: str = "demo-1334882287961657"
    CCC_CALLBACK_TOKEN: str = ""

    # CCC 技能组（在 CCC 控制台 > 实例管理 > 技能组 中获取）
    # 格式: 技能组名称@实例ID，如 jinengzixun@dadong
    CCC_SKILL_GROUP_ID: str = ""              # 技能组 ID

    # 智能机器人坐席前缀 — 用于在 AssignAgent 事件中通过 agentId 识别机器人
    # CCC 中机器人坐席的 agentId 以此前缀开头，如 robot_1@dadong
    # 如果未配置，则通过 agentId 是否含 "robot" 判断
    CCC_ROBOT_AGENT_PREFIX: str = ""

    # RocketMQ 5.x（CCC 事件推送通过 RocketMQ 5.x gRPC SDK 消费）
    ROCKETMQ_ENDPOINT: str = ""
    ROCKETMQ_INSTANCE_ID: str = ""
    ROCKETMQ_TOPIC: str = ""
    ROCKETMQ_GROUP_ID: str = ""
    ROCKETMQ_ACCESS_KEY: str = ""
    ROCKETMQ_ACCESS_SECRET: str = ""

    # Beebot 智能对话机器人（通义版）
    BEEBOT_INSTANCE_ID: str = "chatbot-cn-i7QInbE3jb"
    BEEBOT_AGENT_KEY: str = "e75ee0ab5eab40b1af7d17e2a5342494_p_beebot_public"

    # PostgreSQL
    PG_HOST: str = "localhost"
    PG_PORT: int = 5432
    PG_USER: str = "postgres"
    PG_PASSWORD: str = ""
    PG_DATABASE: str = "ivr_system"

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    # 智能坐席槽位
    ROBOT_SLOT_COUNT: int = 2

    # ── Java 后端 API 地址（Docker 内部服务名）──
    JAVA_API_BASE_URL: str = "http://java-backend:8080"

    # 机器人坐席状态独立数据库（本地 SQLite，与 RDS 工单库隔离）
    ROBOT_DB_PATH: str = "robot_agent.db"

    # 知识库Excel
    KB_EXCEL_PATH: str = "d:\\IVR\\副本知识库导出记录-20260629.xlsx"

    # 知识库上传功能
    KB_UPLOAD_DIR: str = "d:\\IVR\\knowledge-base\\"
    KB_MAX_FILE_SIZE: int = 52428800  # 50MB
    KB_ALLOWED_EXTENSIONS: str = ".xlsx,.xls,.pdf,.txt,.docx,.csv"

    # LLM
    DASHSCOPE_API_KEY: str = ""
    LLM_MODEL: str = "qwen3.7-max"

    # OSS 对象存储（测试报告归档，预留配置项）
    OSS_ENDPOINT: str = ""
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET_NAME: str = ""

    @property
    def pg_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.PG_USER}:{self.PG_PASSWORD}"
            f"@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DATABASE}"
        )

    @property
    def redis_url(self) -> str:
        pwd = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{pwd}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def robot_db_path(self) -> str:
        """返回 SQLite 数据库文件的绝对路径"""
        import os
        if os.path.isabs(self.ROBOT_DB_PATH):
            return self.ROBOT_DB_PATH
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), self.ROBOT_DB_PATH)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # .env 中有未定义的字段时不报错


settings = Settings()