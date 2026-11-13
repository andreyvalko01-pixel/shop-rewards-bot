from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str = "123456:TEST"
    shop_name: str = "Shop Rewards"
    database_url: str = "sqlite+aiosqlite:///data/rewards.sqlite"

    # хто може нараховувати бали і гасити купони прямо з Telegram
    cashier_ids: str = ""

    # бонус за реєстрацію
    welcome_bonus: int = 100

    web_admin_user: str = "admin"
    web_admin_password: str = "admin"

    @property
    def cashiers(self) -> set[int]:
        return {int(x) for x in self.cashier_ids.split(",") if x.strip()}


settings = Settings()
