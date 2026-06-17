# FinFit Telegram Bot

Telegram-бот для клуба FinFit: подписки, Robokassa, GetCourse, автопродление.

## Быстрый старт

```bash
cp .env.example .env
# заполните .env
pip install -r requirements.txt
python bot.py
```

## Деплой на сервер

```powershell
$env:FINBOT_SSH_PASSWORD = "your_root_password"
powershell -ExecutionPolicy Bypass -File deploy_remote.ps1
```

## Robokassa Result URL

```
http://YOUR_SERVER_IP/robokassa/result
```
