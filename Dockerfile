FROM python:3.11-slim

WORKDIR /app

# Install dependencies first
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files
COPY . .

# Expose Admin Port
EXPOSE 8000
# Expose Hosted Sites Port
EXPOSE 8080

CMD ["python", "main.py"]
