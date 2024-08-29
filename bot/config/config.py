from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int = 123
    API_HASH: str = '123'

    USE_DAILY_BOOSTER: bool =  True
    AUTO_PLAY_GAME: bool =  True
    AUTO_TASK: bool = True 
    USE_REF: bool = False
    REF_ID: str = ''
    POINTS: list = [150,300]
    USE_PROXY_FROM_FILE: bool = False


settings = Settings()


