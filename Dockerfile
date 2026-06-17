# Use official Python image
FROM python:3.11

# Set the working directory inside the container
WORKDIR /app

# Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy all files (except ones in .dockerignore)
COPY . .

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Add this line somewhere after setting up Python
RUN pip install --no-cache-dir gunicorn

# Collect static files inside the container during build
RUN python manage.py collectstatic --noinput

# Expose Django's new port
EXPOSE 8080

# Start with gunicorn (overridden by docker-compose, but consistent)
CMD ["gunicorn", "purchase_order.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "3"]
