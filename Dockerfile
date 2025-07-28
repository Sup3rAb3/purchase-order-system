# Use official Python image
FROM python:3.11

# Set the working directory inside the container
WORKDIR /app

# Copy all files (except ones in .dockerignore)
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose Django's new port
EXPOSE 8080

# Start Django app on port 8080
CMD ["python", "manage.py", "runserver", "0.0.0.0:8080"]
