from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int = 123
    API_HASH: str = '123'

    AUTO_PLAY_GAME: bool =  True
    AUTO_TASK: bool = True 
    POINTS: list = [150,300]

    REF_ID: str = ''

    USE_PROXY_FROM_FILE: bool = False


settings = Settings()


