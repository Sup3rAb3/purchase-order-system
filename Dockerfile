# 1. Use the official Python image
FROM python:3.11

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Prevent Python from writing pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 4. Copy ONLY requirements.txt first so Docker grabs your fresh local file
COPY requirements.txt /app/

# 5. Install all Python dependencies inside the image (including Gunicorn)
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# 6. NOW copy the rest of your app files over
COPY . /app/

# 7. Collect static files inside the container safely now that Django is installed
RUN python manage.py collectstatic --noinput

# 8. Expose Django's new port
EXPOSE 8080

# 9. Start with gunicorn
CMD ["gunicorn", "purchase_order.wsgi:application", "--bind", "0.0.0.0:8080", "--workers", "3"]