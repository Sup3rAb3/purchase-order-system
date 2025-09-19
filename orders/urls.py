# orders/urls.py
from django.urls import path
from . import views
from allauth.account.views import LoginView  # Add this import for LoginView


urlpatterns = [
    path('', LoginView.as_view(), name='account_login'),  # Set root URL to login page
    path('create/', views.create_purchase_order, name='create_purchase_order'),
    path('logout/', views.custom_logout, name='custom_logout'),
    path('get_approvers/', views.get_approvers, name='get_approvers'),
    path('approve/<str:token>/', views.approve_po, name='approve_po'),
    path('deny/<str:token>/', views.deny_po, name='deny_po'),
    path('petty-cash/', views.create_petty_cash, name='create_petty_cash'), #view petty cash url
    path('api/exchange-rates/', views.exchange_rates_api, name='exchange_rates_api'),
    path('finance-dashboard/', views.finance_dashboard, name='finance_dashboard'),
]