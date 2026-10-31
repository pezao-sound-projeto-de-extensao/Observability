FROM python:3.13.5-slim

RUN pip install --no-cache-dir boto3==1.43.123

COPY reader.py /app/reader.py

# O volume nomeado herda esse dono na primeira montagem
RUN useradd --uid 10001 --no-create-home reader && mkdir /var/lib/cloudwatch-reader && chown reader /var/lib/cloudwatch-reader
USER reader

CMD ["python", "-u", "/app/reader.py"]
