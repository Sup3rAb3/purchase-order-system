"""
URL configuration for purchase_order project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.urls import path
from orders.views import approve_po, deny_po
from orders.views import create_purchase_order  # Ensure this import is correct

urlpatterns = [
    path('admin/', admin.site.urls),  # Admin URL
    path('accounts/', include('allauth.urls')),  # Allauth URLs
    path('create/', create_purchase_order, name='create_purchase_order'),  # Create Purchase Order URL
    path('approve/<str:token>/', approve_po, name='approve_purchase_order'), # Approve Purchase Order
    path('deny/<str:token>/', deny_po, name='deny_purchase_order'), # Deny Purchase
]