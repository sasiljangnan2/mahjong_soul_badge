FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway / Render 등은 PORT 환경변수를 동적으로 지정함
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}
