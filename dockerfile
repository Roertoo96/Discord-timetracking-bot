services:
  prostbot:
    image: python:3.12-slim
    container_name: discord-time-bot
    restart: always
    working_dir: /app
    volumes:
      - discord-time-bot_data:/app
    command: /bin/sh -c "
      apt-get update && \
      pip install --upgrade pip && \
      pip install -r requirements.txt && \
      python bot.py"
    environment:
      - DISCORD_TOKEN=dein token

volumes:
  discord-time-bot_data:
