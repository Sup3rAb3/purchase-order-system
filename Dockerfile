# Use official Python image
FROM python:3.11

# Set the working directory inside the container
WORKDIR /app

# Copy all files (except ones in .dockerignore)
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Add this line somewhere after setting up Python
RUN pip install --no-cache-dir gunicorn

# Expose Django's new port
EXPOSE 8080

# Start with gunicorn (overridden by docker-compose, but consistent)
CMD ["gunicorn", "purchase_order.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "3"]
