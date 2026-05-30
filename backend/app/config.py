from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parents[1]


class Settings:
    app_name = os.getenv("APP_NAME", "鼠鼠视频下载工具")
    env = os.getenv("APP_ENV", "development")
    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

    data_dir = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
    download_dir = Path(os.getenv("DOWNLOAD_DIR", data_dir / "downloads"))

    cors_origins = [
        item.strip()
        for item in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if item.strip()
    ]


settings = Settings()


def ensure_data_dirs() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.download_dir.mkdir(parents=True, exist_ok=True)
