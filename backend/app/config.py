from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "长信宫灯烟道流体仿真与室内空气质量分析系统"
    API_V1_PREFIX: str = "/api"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/changxin_gongdeng"

    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: Optional[str] = None
    MQTT_PASSWORD: Optional[str] = None
    MQTT_TOPIC_ALERT: str = "gongdeng/alerts"
    MQTT_TOPIC_DATA: str = "gongdeng/sensor"

    PM25_THRESHOLD_WARNING: float = 75.0
    PM25_THRESHOLD_CRITICAL: float = 150.0
    FLUE_VELOCITY_MIN: float = 0.1
    FLUE_TEMPERATURE_MAX: float = 200.0

    MODBUS_HOST: str = "localhost"
    MODBUS_PORT: int = 502

    ROOM_SIZE_X: float = 10.0
    ROOM_SIZE_Y: float = 8.0
    ROOM_SIZE_Z: float = 3.0
    GRID_RESOLUTION: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
