# Use official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install dependencies (from python_client_app/requirements.txt)
COPY python_client_app/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the client app code
COPY python_client_app python_client_app

# Expose port
EXPOSE 8001

# Run the application
CMD ["uvicorn", "python_client_app.main:app", "--host", "0.0.0.0", "--port", "8001"]
