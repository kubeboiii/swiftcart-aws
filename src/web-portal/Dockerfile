# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependency file and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application logic
COPY web_portal.py .

# Expose port 80 to the Docker host
EXPOSE 80

# Command to run the application
CMD ["python", "web_portal.py"]
