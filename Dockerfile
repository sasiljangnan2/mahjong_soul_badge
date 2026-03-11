FROM python:3.11-slim

WORKDIR /app

# 의존성 설치 (변경 없으면 캐시 재사용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드만 선택적으로 복사 (data/ 제외)
COPY *.py ./
COPY assets/ ./assets/
COPY ms/ ./ms/

# 런타임 데이터 디렉토리 생성
RUN mkdir -p data/players

EXPOSE 8000

# Railway는 PORT를 자동 설정하므로, 고정값이 아닌 환경변수 사용
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000}"]
