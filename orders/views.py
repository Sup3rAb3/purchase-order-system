from django.conf import settings
from django.utils import timezone
from orders.utils import request_approval, get_approvers_for_amount
from django.contrib.auth import logout
from django.contrib.messages import get_messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.mail import send_mail, EmailMessage
from django.utils.crypto import get_random_string
from django.http import HttpResponse, JsonResponse
from django.utils.timezone import now
import requests 
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from django.templatetags.static import static
from datetime import timedelta, datetime
from decimal import Decimal
from django.db.models import Sum, Count, Q, F
from .models import PurchaseOrder, PurchaseOrderItem, SignatoryApproval, PettyCashRequest, Approver, ExchangeRate
from .forms import PurchaseOrderForm, PurchaseOrderItemFormSet, PettyCashForm, QuotationFormSet
import os
import csv
import json
import logging  # Add logging for debugging
# Set up logging
logger = logging.getLogger(__name__)

def exchange_rates_api(request):
    rates = ExchangeRate.objects.all()
    rates_dict = {
        rate.currency: {
            "rate_to_usd": float(rate.rate_to_usd) if rate.rate_to_usd is not None else 0.0,
        }
        for rate in rates
    }
    return JsonResponse(rates_dict)

DEPARTMENT_APPROVERS = {  #Department approvers array
    'DRPP': [
        {'name': 'Sydney Chisenga', 'email': 'abfr2x@gmail.com', 'role': 'Department Approver'},
        {'name': 'General Manager', 'email': 'abrahammanda.ac@gmail.com', 'role': 'General Manager'},
        {'name': 'Finance Manager', 'email': 'mandaabraham7@gmail.com', 'role': 'Finance Manager'},
    ],
    'B&F': [
        {'name': 'Lupiya Simusokwe', 'email': 'abfr2x@gmail.com', 'role': 'Department Approver'},
        {'name': 'General Manager', 'email': 'abrahammanda.ac@gmail.com', 'role': 'General Manager'},
        {'name': 'Finance Manager', 'email': 'mandaabraham7@gmail.com', 'role': 'Finance Manager'},
    ],
    'CA': [
        {'name': 'Jackie Jhala', 'email': 'abfr2x@gmail.com', 'role': 'Department Approver'},
        {'name': 'General Manager', 'email': 'abrahammanda.ac@gmail.com', 'role': 'General Manager'},
        {'name': 'Finance Manager', 'email': 'mandaabraham7@gmail.com', 'role': 'Finance Manager'},
    ],
    'ERI': [
        {'name': 'Mutinta Zulu', 'email': 'abfr2x@gmail.com', 'role': 'Department Approver'},
        {'name': 'General Manager', 'email': 'abrahammanda.ac@gmail.com', 'role': 'General Manager'},
        {'name': 'Finance Manager', 'email': 'mandaabraham7@gmail.com', 'role': 'Finance Manager'},
    ],
}

NON_LEGAL_APPROVERS = {
    'mandaabraham7@gmail.com': {'name': 'Finance Manager', 'role': 'Finance Manager'},
    'abfr2x@gmail.com': {'name': 'Senior Accountant', 'role': 'Senior Accountant'},
}

@login_required
def finance_dashboard(request):
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    currency_filter = request.GET.get('currency', 'all')
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() + timedelta(days=1)
        except ValueError:
            start_date = (timezone.now() - timedelta(days=30)).date()
            end_date = timezone.now().date() + timedelta(days=1)
    else:
        start_date = (timezone.now() - timedelta(days=30)).date()
        end_date = timezone.now().date() + timedelta(days=1)

    supported_currencies = ['ZMW', 'USD', 'EUR', 'ZAR']

    po_base_query = PurchaseOrder.objects.filter(created_at__date__gte=start_date, created_at__date__lt=end_date)
    pc_base_query = PettyCashRequest.objects.filter(created_at__date__gte=start_date, created_at__date__lt=end_date)
    
    if currency_filter != 'all':
        po_base_query = po_base_query.filter(items__currency=currency_filter).distinct()

    pending_po_approvals = SignatoryApproval.objects.filter(
        purchase_order__status='Pending',
        approved__isnull=True,
        purchase_order__created_at__date__gte=start_date,
        purchase_order__created_at__date__lt=end_date
    ).select_related('purchase_order', 'purchase_order__requester').order_by('-purchase_order__created_at')
    
    pending_pc_approvals = SignatoryApproval.objects.filter(
        petty_cash_request__status='Pending',
        approved__isnull=True,
        petty_cash_request__created_at__date__gte=start_date,
        petty_cash_request__created_at__date__lt=end_date
    ).select_related('petty_cash_request', 'petty_cash_request__requester').order_by('-petty_cash_request__created_at')
    
    if currency_filter != 'all':
        pending_po_approvals = pending_po_approvals.filter(purchase_order__items__currency=currency_filter).distinct()

    currency_stats = []
    for currency in supported_currencies:
        pos = po_base_query.filter(items__currency=currency).distinct()
        pcs = pc_base_query if currency == 'ZMW' else PettyCashRequest.objects.none()
        po_count = pos.count()
        pc_count = pcs.count()
        po_total = pos.aggregate(total=Sum(F('total_amount')))['total'] or Decimal('0')
        po_total_zmw = sum(
            po.total_amount_in_zmw() or po.total_amount for po in pos
        )
        pc_total = pcs.aggregate(total=Sum(F('amount')))['total'] or Decimal('0')
        currency_stats.append({
            'currency': currency,
            'po_count': po_count,
            'po_total': float(po_total),
            'po_total_zmw': float(po_total_zmw),
            'pc_count': pc_count,
            'pc_total': float(pc_total),
        })

    # Fetch exchange rates from the ExchangeRate model
    exchange_rates = ExchangeRate.objects.all().values('currency', 'rate_to_usd')
    logger.info(f"Exchange rates fetched: {list(exchange_rates)}")

    # Calculate rates to ZMW
    zmw_rate_to_usd = next((rate['rate_to_usd'] for rate in exchange_rates if rate['currency'] == 'ZMW'), None)
    if zmw_rate_to_usd:
        usd_to_zmw = 1 / float(zmw_rate_to_usd)  # Convert to float for calculation
        exchange_rates = [
            {
                'currency': rate['currency'],
                'rate_to_usd': float(rate['rate_to_usd']),
                'rate_to_zmw': float(rate['rate_to_usd']) * usd_to_zmw
            }
            for rate in exchange_rates
        ]
    else:
        exchange_rates = list(exchange_rates)  # Fallback to original data if ZMW rate not found

    # Pie chart data for PO totals by currency (ZMW)
    pie_chart_data = {
        'labels': [stat['currency'] for stat in currency_stats if stat['po_total_zmw'] > 0],
        'datasets': [{
            'data': [stat['po_total_zmw'] for stat in currency_stats if stat['po_total_zmw'] > 0],
            'backgroundColor': ['#4F46E5', '#10B981', '#F59E0B', '#EF4444'],
            'borderColor': '#ffffff',
            'borderWidth': 2
        }]
    }
    pie_chart_data_json = json.dumps(pie_chart_data)

    approval_stats = SignatoryApproval.objects.filter(
        approved__isnull=False,
        updated_at__date__gte=start_date,
        updated_at__date__lt=end_date
    ).select_related('purchase_order', 'petty_cash_request').order_by('-updated_at')
    
    if currency_filter != 'all':
        approval_stats = approval_stats.filter(
            Q(purchase_order__items__currency=currency_filter) |
            Q(petty_cash_request__isnull=False)
        ).distinct()

    dates = [(start_date + timedelta(days=x)).strftime('%Y-%m-%d') for x in range((end_date - start_date).days)]
    graph_data = {
        'labels': dates,
        'datasets': []
    }
    
    for currency in supported_currencies:
        for status in ['Pending', 'Approved', 'Rejected']:
            po_data = []
            pc_data = []
            for date in dates:
                date_obj = datetime.strptime(date, '%Y-%m-%d').date()
                po_count = po_base_query.filter(
                    status=status,
                    created_at__date=date_obj,
                    items__currency=currency
                ).distinct().count()
                pc_count = pc_base_query.filter(
                    status=status,
                    created_at__date=date_obj
                ).count() if currency == 'ZMW' else 0
                po_data.append(po_count)
                pc_data.append(pc_count)
            if sum(po_data) > 0:
                graph_data['datasets'].append({
                    'label': f'PO {status} ({currency})',
                    'data': po_data,
                    'backgroundColor': {
                        'Pending': '#ff9800',
                        'Approved': '#4caf50',
                        'Rejected': '#f44336'
                    }[status],
                    'stack': f'PO_{currency}'
                })
            if sum(pc_data) > 0 and currency == 'ZMW':
                graph_data['datasets'].append({
                    'label': f'PC {status} (ZMW)',
                    'data': pc_data,
                    'backgroundColor': {
                        'Pending': '#ffb300',
                        'Approved': '#66bb6a',
                        'Rejected': '#ef5350'
                    }[status],
                    'stack': 'PC_ZMW'
                })

    graph_data_json = json.dumps(graph_data)

    total_pending = pending_po_approvals.count() + pending_pc_approvals.count()
    overdue_approvals = SignatoryApproval.objects.filter(
        approved__isnull=True,
        created_at__lte=timezone.now() - timedelta(hours=24)
    ).count()
    
    approval_times = approval_stats.filter(approved=True).values('created_at', 'updated_at')
    total_approval_time = sum(
        (approval['updated_at'] - approval['created_at']).total_seconds()
        for approval in approval_times
    )
    avg_approval_time_hours = round(total_approval_time / 3600 / max(1, len(approval_times)), 2)

    current_month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    approved_pos = PurchaseOrder.objects.filter(
        status='Approved',
        created_at__gte=current_month_start
    )
    approved_pcs = PettyCashRequest.objects.filter(
        status='Approved',
        created_at__gte=current_month_start
    )
    
    zmw_total_po = sum(
        po.total_amount_in_zmw() or po.total_amount for po in approved_pos
    )
    zmw_total_pc = approved_pcs.aggregate(total=Sum(F('amount')))['total'] or Decimal('0')
    
    department_summary = approved_pos.values('department').annotate(
        count=Count('id'),
        total_amount_zmw=Sum(F('total_amount'))
    )

    # Approved and Denied Purchase Orders
    approved_pos_filtered = approved_pos
    denied_pos = po_base_query.filter(status='Rejected')
    if currency_filter != 'all':
        approved_pos_filtered = approved_pos_filtered.filter(items__currency=currency_filter).distinct()
        denied_pos = denied_pos.filter(items__currency=currency_filter).distinct()

    total_approved_po_count = approved_pos_filtered.count()
    total_denied_po_count = denied_pos.count()
    total_approved_po_amount = sum(
        po.total_amount_in_zmw() or po.total_amount for po in approved_pos_filtered
    )
    total_denied_po_amount = sum(
        po.total_amount_in_zmw() or po.total_amount for po in denied_pos
    )

    # Approved and Denied Petty Cash Requests
    approved_pcs_filtered = approved_pcs.filter(status='Approved')
    denied_pcs = pc_base_query.filter(status='Rejected')
    # Only apply currency filter if it's ZMW, since PCs are ZMW-only
    if currency_filter != 'all' and currency_filter == 'ZMW':
            approved_pcs_filtered = PettyCashRequest.objects.none()
            denied_pcs = PettyCashRequest.objects.none()
    
    total_approved_pc_count = approved_pcs_filtered.count()
    total_denied_pc_count = denied_pcs.count()
    total_approved_pc_amount = approved_pcs_filtered.aggregate(total=Sum(F('amount')))['total'] or Decimal('0')
    total_denied_pc_amount = denied_pcs.aggregate(total=Sum(F('amount')))['total'] or Decimal('0')

    # New Metrics
    # Total Pending Amount
    pending_pos = po_base_query.filter(status='Pending')
    pending_pcs = pc_base_query.filter(status='Pending')
    if currency_filter != 'all':
        pending_pos = pending_pos.filter(items__currency=currency_filter).distinct()
        # No currency filter for PCs since they are ZMW-only
    total_pending_amount = sum(
        (po.total_amount_in_zmw() or po.total_amount for po in pending_pos),
        Decimal('0')
    ) + sum(
        (pc.amount for pc in pending_pcs),
        Decimal('0')
    )

    # Total Overdue Amount
    overdue_pos = pending_pos.filter(created_at__lte=timezone.now() - timedelta(hours=24))
    overdue_pcs = pending_pcs.filter(created_at__lte=timezone.now() - timedelta(hours=24))
    total_overdue_amount = sum(
        (po.total_amount_in_zmw() or po.total_amount for po in overdue_pos),
        Decimal('0')
    ) + sum(
        (pc.amount for pc in overdue_pcs),
        Decimal('0')
    )

    # Total Approved Amount (PO + PC)
    total_approved_amount = total_approved_po_amount + total_approved_pc_amount

    export_type = request.GET.get('export')
    if export_type:
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{export_type}_report_{start_date}_{end_date_str}.csv"'
        writer = csv.writer(response)

        if export_type == 'currency_stats':
            writer.writerow(['Currency', 'PO Count', 'PO Total', 'PO Total (ZMW)', 'PC Count', 'PC Total'])
            for stat in currency_stats:
                writer.writerow([
                    stat['currency'],
                    stat['po_count'],
                    f"{stat['po_total']:.2f}",
                    f"{stat['po_total_zmw']:.2f}",
                    stat['pc_count'],
                    f"{stat['pc_total']:.2f}"
                ])
        
        elif export_type == 'approval_stats':
            writer.writerow(['Type', 'Number', 'Role', 'Action', 'Signed By', 'Updated At'])
            for approval in approval_stats:
                type_ = 'Purchase Order' if approval.purchase_order else 'Petty Cash'
                number = approval.purchase_order.purchase_order_number if approval.purchase_order else approval.petty_cash_request.petty_cash_number
                writer.writerow([
                    type_,
                    number,
                    approval.role,
                    'Approved' if approval.approved else 'Denied',
                    approval.signed_by_name or 'Unknown',
                    approval.updated_at.strftime('%Y-%m-%d %H:%M')
                ])
        
        elif export_type == 'pending':
            writer.writerow(['Type', 'Number', 'Requester', 'Amount', 'Currency', 'Role', 'Created At', 'Overdue'])
            for approval in pending_po_approvals:
                po = approval.purchase_order
                currency = po.items.first().currency if po.items.exists() else 'ZMW'
                overdue = timezone.now() - approval.created_at > timedelta(hours=24)
                writer.writerow([
                    'Purchase Order',
                    po.purchase_order_number,
                    po.requester.username,
                    f"{po.total_amount:.2f}",
                    currency,
                    approval.role,
                    po.created_at.strftime('%Y-%m-%d %H:%M'),
                    'Yes' if overdue else 'No'
                ])
            for approval in pending_pc_approvals:
                pc = approval.petty_cash_request
                overdue = timezone.now() - approval.created_at > timedelta(hours=24)
                writer.writerow([
                    'Petty Cash',
                    pc.petty_cash_number,
                    pc.requester.username,
                    f"{pc.amount:.2f}",
                    'ZMW',
                    approval.role,
                    pc.created_at.strftime('%Y-%m-%d %H:%M'),
                    'Yes' if overdue else 'No'
                ])
        elif export_type == 'approval_summary':
            writer.writerow([
                'Total Approved POs', 'Total Denied POs', 'Approved PO Amount (ZMW)', 'Denied PO Amount (ZMW)',
                'Total Approved Petty Cash', 'Total Denied Petty Cash', 'Approved Petty Cash Amount (ZMW)', 'Denied Petty Cash Amount (ZMW)',
                'Total Pending Amount (ZMW)', 'Total Overdue Amount (ZMW)', 'Total Approved Amount (ZMW)'
            ])
            writer.writerow([
                total_approved_po_count, total_denied_po_count, f"{total_approved_po_amount:.2f}", f"{total_denied_po_amount:.2f}",
                total_approved_pc_count, total_denied_pc_count, f"{total_approved_pc_amount:.2f}", f"{total_denied_pc_amount:.2f}",
                f"{total_pending_amount:.2f}", f"{total_overdue_amount:.2f}", f"{total_approved_amount:.2f}"
            ])

        return response

    context = {
        'pending_po_approvals': pending_po_approvals,
        'pending_pc_approvals': pending_pc_approvals,
        'currency_stats': currency_stats,
        'approval_stats': approval_stats,
        'graph_data_json': graph_data_json,
        'pie_chart_data_json': pie_chart_data_json,
        'zmw_total_po': float(zmw_total_po),
        'zmw_total_pc': float(zmw_total_pc),
        'department_summary': department_summary,
        'total_pending': total_pending,
        'overdue_approvals': overdue_approvals,
        'avg_approval_time_hours': avg_approval_time_hours,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': (end_date - timedelta(days=1)).strftime('%Y-%m-%d'),
        'currency_filter': currency_filter,
        'supported_currencies': supported_currencies,
        'exchange_rates': exchange_rates,
        'total_approved_po_count': total_approved_po_count,
        'total_denied_po_count': total_denied_po_count,
        'total_approved_po_amount': float(total_approved_po_amount),
        'total_denied_po_amount': float(total_denied_po_amount),
        'total_approved_pc_count': total_approved_pc_count,
        'total_denied_pc_count': total_denied_pc_count,
        'total_approved_pc_amount': float(total_approved_pc_amount),
        'total_denied_pc_amount': float(total_denied_pc_amount),
        'total_pending_amount': float(total_pending_amount),
        'total_overdue_amount': float(total_overdue_amount),
        'total_approved_amount': float(total_approved_amount),
    }
    return render(request, 'orders/finance_dashboard.html', context)
@login_required
def create_purchase_order(request):
    print(f"Session ID: {request.session.session_key}")
    if request.method == "POST":
        po_form = PurchaseOrderForm(request.POST)
        item_formset = PurchaseOrderItemFormSet(request.POST)
        quotation_formset = QuotationFormSet(request.POST, request.FILES)
        
        if po_form.is_valid() and item_formset.is_valid() and quotation_formset.is_valid():
            purchase_order = po_form.save(commit=False)
            purchase_order.requester = request.user
            purchase_order.status = 'Pending'
            purchase_order.save()

            items = item_formset.save(commit=False)
            for item in items:
                item.purchase_order = purchase_order
                item.save()

            quotations = quotation_formset.save(commit=False)
            for quotation in quotations:
                quotation.purchase_order = purchase_order
                quotation.save()

            purchase_order.calculate_totals()

            # Convert total amount to ZMW
            total_amount_zmw = purchase_order.total_amount_in_zmw() or purchase_order.total_amount
            
            # Block amounts less than or equal to 1,000 ZMW
            if total_amount_zmw <= Decimal('1000.00'):
                messages.error(request, f'Purchase order total must exceed 1,000 ZMW. Converted amount: {total_amount_zmw:.2f} ZMW. For amounts of 1,000 ZMW or less, please use a petty cash request.')
            else:
                # Get approvers based on ZMW amount and department
                approvers = get_approvers_for_amount(purchase_order)
                if not approvers:
                    messages.error(request, f'No approvers found for amount {total_amount_zmw:.2f} ZMW in department {purchase_order.department}.')
                else:
                    success, message = request_approval(purchase_order)
                    if success:
                        messages.success(request, message)
                        po_form = PurchaseOrderForm()
                        item_formset = PurchaseOrderItemFormSet()
                        quotation_formset = QuotationFormSet()
                    else:
                        messages.error(request, message)
        else:
            print("PO Form Errors:", po_form.errors)
            print("Item Formset Errors:", item_formset.errors)
            print("Quotation Formset Errors:", quotation_formset.errors)
    else:
        po_form = PurchaseOrderForm()
        item_formset = PurchaseOrderItemFormSet()
        quotation_formset = QuotationFormSet()

    return render(request, "orders/create_po.html", {
        "po_form": po_form,
        "item_formset": item_formset,
        "quotation_formset": quotation_formset,
    })

@login_required
def create_petty_cash(request):
    if request.method == "POST":
        form = PettyCashForm(request.POST)
        if form.is_valid():
            petty_cash = form.save(commit=False)
            petty_cash.requester = request.user
            petty_cash.status = 'Pending'
            if petty_cash.amount > 1000:
                messages.error(request, 'Petty cash requests must be ≤ 1,000.')
                return redirect('create_petty_cash')
            petty_cash.save()

            if petty_cash.is_legal:
                if not petty_cash.selected_approver_email or not petty_cash.department:
                    messages.error(request, 'Please select an approver and department for legal petty cash.')
                    return redirect('create_petty_cash')
                approvers = DEPARTMENT_APPROVERS.get(petty_cash.department, DEPARTMENT_APPROVERS['DRPP'])
                selected_approver = next((a for a in approvers if a['email'] == petty_cash.selected_approver_email), None)
                role = selected_approver['role'] if selected_approver else "Finance Manager"
                approval = SignatoryApproval.objects.create(
                    petty_cash_request=petty_cash,
                    role=role
                )
            else:
                if not petty_cash.non_legal_approver_email:
                    messages.error(request, 'Please select an approver for non-legal petty cash.')
                    return redirect('create_petty_cash')
                approver = NON_LEGAL_APPROVERS.get(petty_cash.non_legal_approver_email, None)
                if not approver:
                    messages.error(request, 'Invalid approver selected for non-legal petty cash.')
                    return redirect('create_petty_cash')
                role = approver['role']
                approval = SignatoryApproval.objects.create(
                    petty_cash_request=petty_cash,
                    role=role
                )
            approval.send_approval_email()
            messages.success(request, 'Petty cash request submitted!')
            return redirect('create_petty_cash')
        else:
            print("Petty Cash Form Errors:", form.errors)
    else:
        form = PettyCashForm()
    return render(request, "orders/create_petty_cash.html", {"form": form})

def send_final_decision_email(approval, decision, pdf_url=None):
    decision = decision.lower()
    recipients = set()
    finance_team_email = "abraham96manda@gmail.com"

    if approval.purchase_order:
        po = approval.purchase_order
        if po.requester and hasattr(po.requester, 'email'):
            recipients.add(po.requester.email)
        recipients.add(approval.get_recipient_email())
        recipients.add(finance_team_email)

        subject = f"Purchase Order {decision.title()} - {po.purchase_order_number}"
        currency = po.items.first().currency if po.items.exists() else 'ZMW'
        decision_details = []
        for approval in po.approvals.all():
            if approval.approved is not None:
                approver_text = f"{approval.role}"
                if approval.on_behalf_of:
                    approver_text += f" (on behalf of {approval.on_behalf_of.role})"
                decision_details.append(
                    f"{approver_text}: {'Approved' if approval.approved else 'Denied'} by {approval.signed_by_name or 'Unknown'}"
                )
        email_body = f"""
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
            <title>Purchase Order {decision.title()}</title>
            <style type="text/css">
                body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
            </style>
        </head>
        <body style="background-color: #f4f4f4; padding: 20px;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                    <td align="center">
                        <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                            <tr>
                                <td>
                                    <h2 style="color: #333;">Purchase Order {decision.title()}</h2>
                                    <p><strong>PO Number:</strong> {po.purchase_order_number}</p>
                                    <p><strong>Requester:</strong> {po.requester.username if po.requester else 'N/A'}</p>
                                    <p><strong>Destination:</strong> {po.destination}</p>
                                    <p><strong>Total Amount:</strong> {currency} {po.total_amount:,.2f}</p>

                                    <h3>Decision History</h3>
                                    <p>{chr(10).join(decision_details) or 'No decisions yet'}</p>

                                    <h3>Next Steps</h3>
                                    <p>{ "The requester will proceed with the order. Download the approved PO here: " + (pdf_url or "") if decision == "approved" else "Please contact the requester for alternatives."}</p>

                                    <p>This is an automated notification. Please do not reply directly.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    elif approval.petty_cash_request:
        pc = approval.petty_cash_request
        if pc.requester and hasattr(pc.requester, 'email'):
            recipients.add(pc.requester.email)
        if pc.is_legal and pc.selected_approver_email:
            recipients.add(pc.selected_approver_email)
        elif not pc.is_legal and pc.non_legal_approver_email:
            recipients.add(pc.non_legal_approver_email)
        recipients.add(finance_team_email)

        subject = f"Petty Cash {decision.title()} - {pc.petty_cash_number}"
        decision_details = [
            f"{approval.role}: {'Approved' if approval.approved else 'Denied'} by {approval.signed_by_name or 'Unknown'}"
            for approval in pc.approvals.all() if approval.approved is not None
        ]
        email_body = f"""
        <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
        <html xmlns="http://www.w3.org/1999/xhtml">
        <head>
            <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
            <title>Petty Cash {decision.title()}</title>
            <style type="text/css">
                body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
                table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
            </style>
        </head>
        <body style="background-color: #f4f4f4; padding: 20px;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                    <td align="center">
                        <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                            <tr>
                                <td>
                                    <h2 style="color: #333;">Petty Cash {decision.title()}</h2>
                                    <p><strong>Number:</strong> {pc.petty_cash_number}</p>
                                    <p><strong>Requester:</strong> {pc.requester.username if pc.requester else 'N/A'}</p>
                                    <p><strong>Amount:</strong> ZMW {pc.amount:,.2f}</p>
                                    <p><strong>Client:</strong> {pc.client}</p>
                                    <p><strong>Matter ID:</strong> {pc.matter_id}</p>

                                    <h3>Decision History</h3>
                                    <p>{chr(10).join(decision_details) or 'No decisions yet'}</p>

                                    <h3>Next Steps</h3>
                                    <p>{ "The requester will proceed with the request. Download the approved request here: " + (pdf_url or "") if decision == "approved" else "Please contact the requester for alternatives."}</p>

                                    <p>This is an automated notification. Please do not reply directly.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    if recipients:
        send_mail(
            subject=subject,
            message=email_body,
            from_email="amanda@corpus.co.zm",
            recipient_list=list(recipients),
            fail_silently=False,
            html_message=email_body,
        )

def send_petty_cash_approved_email(petty_cash, pdf_url):
    subject = f"Petty Cash Approved - {petty_cash.petty_cash_number}"
    recipients = set()
    finance_team_email = "abraham96manda@gmail.com"

    if petty_cash.requester and hasattr(petty_cash.requester, 'email'):
        recipients.add(petty_cash.requester.email)
    if petty_cash.is_legal and petty_cash.selected_approver_email:
        recipients.add(petty_cash.selected_approver_email)
    elif not petty_cash.is_legal and petty_cash.non_legal_approver_email:
        recipients.add(petty_cash.non_legal_approver_email)
    recipients.add(finance_team_email)

    approval = petty_cash.approvals.first()
    signed_by = approval.signed_by_name if approval and approval.signed_by_name else "Unknown"
    message = f"""
    <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
    <html xmlns="http://www.w3.org/1999/xhtml">
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
        <title>Petty Cash Approved</title>
        <style type="text/css">
            body {{ font-family: sans-serif; -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
            table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
        </style>
    </head>
    <body style="background-color: #f4f4f4; padding: 20px;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0">
            <tr>
                <td align="center">
                    <table width="600" border="0" cellspacing="0" cellpadding="20" style="background-color: white; border-radius: 8px;">
                        <tr>
                            <td>
                                <h2 style="color: #333;">Petty Cash Approved</h2>
                                <p><strong>Number:</strong> {petty_cash.petty_cash_number}</p>
                                <p><strong>Requester:</strong> {petty_cash.requester.username}</p>
                                <p><strong>Amount:</strong> ZMW {petty_cash.amount}</p>
                                <p><strong>Client:</strong> {petty_cash.client}</p>
                                <p><strong>Matter ID:</strong> {petty_cash.matter_id}</p>
                                <p><strong>Signed By:</strong> {signed_by}</p>
                                <p><strong>Download:</strong> <a href="{pdf_url}">Petty Cash PDF</a></p>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email="amanda@corpus.co.zm",
            recipient_list=list(recipients),
            fail_silently=False,
            html_message=message,
        )
    except Exception as e:
        print(f"Failed to send petty cash approved email: {e}")

def approve_po(request, token):
    approval = get_object_or_404(SignatoryApproval, approval_token=token)
    approval.approved = True
    if approval.petty_cash_request and approval.petty_cash_request.is_legal:
        approvers = DEPARTMENT_APPROVERS.get(approval.petty_cash_request.department, DEPARTMENT_APPROVERS['DRPP'])
        selected_approver = next((a for a in approvers if a['email'] == approval.petty_cash_request.selected_approver_email), None)
        approval.signed_by_name = selected_approver['name'] if selected_approver else approval.role
    else:
        approval.signed_by_name = approval.role
    approval.save()

    if approval.purchase_order:
        po = approval.purchase_order
        po.update_approval_status()
    
        if po.status == "Approved":
            pdf_url = f"http://{settings.SITE_DOMAIN}{generate_po_pdf(po)}"
            send_final_decision_email(approval, "approved", pdf_url)
        elif po.status == "Rejected":
            send_final_decision_email(approval, "denied")
        
        return HttpResponse(f"Approval recorded. PO status: {po.status}.")
    elif approval.petty_cash_request:
        petty_cash = approval.petty_cash_request
        petty_cash.status = "Approved"
        petty_cash.save()
        pdf_url = f"http://{settings.SITE_DOMAIN}{generate_petty_cash_pdf(petty_cash)}"
        send_petty_cash_approved_email(petty_cash, pdf_url)
        approval.send_final_decision_email("approved")
        return HttpResponse("Petty cash approval successful. Thank you.")

def deny_po(request, token):
    approval = get_object_or_404(SignatoryApproval, approval_token=token)
    approval.approved = False
    if approval.petty_cash_request and approval.petty_cash_request.is_legal:
        approvers = DEPARTMENT_APPROVERS.get(approval.petty_cash_request.department, DEPARTMENT_APPROVERS['DRPP'])
        selected_approver = next((a for a in approvers if a['email'] == approval.petty_cash_request.selected_approver_email), None)
        approval.signed_by_name = selected_approver['name'] if selected_approver else approval.role
    else:
        approval.signed_by_name = approval.role
    approval.save()
    
    if approval.purchase_order:
        po = approval.purchase_order
        po.update_approval_status()
        send_final_decision_email(approval, "denied")
        return HttpResponse("Purchase order denied.")
    elif approval.petty_cash_request:
        petty_cash = approval.petty_cash_request
        petty_cash.status = "Rejected"
        petty_cash.save()
        approval.send_final_decision_email("rejected")
        return HttpResponse("Petty cash request denied.")
    
def get_approvers(request):
    department = request.GET.get('department', 'DRPP')
    print(f"Received department: {department}")
    approvers = DEPARTMENT_APPROVERS.get(department, DEPARTMENT_APPROVERS['DRPP'])
    print(f"Selected approvers for department {department}: {approvers}")
    seen_emails = set()
    unique_approvers = []
    for approver in approvers:
        if approver['email'] not in seen_emails:
            seen_emails.add(approver['email'])
            unique_approvers.append(approver)
    return JsonResponse({'approvers': unique_approvers})

def generate_po_pdf(purchase_order):
    filename = f"PO_{purchase_order.purchase_order_number}.pdf"
    filepath = os.path.join("media/purchase_orders", filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    margin = 50
    content_width = width - 2 * margin
    
    c.setLineWidth(1)
    c.rect(margin, height - 120, content_width, 70)
    try:
        logo_path = os.path.join(settings.STATIC_ROOT, 'images', 'logo-official.png')
        if not os.path.exists(logo_path):
            static_dirs = getattr(settings, 'STATICFILES_DIRS', [])
            for static_dir in static_dirs:
                logo_path = os.path.join(static_dir, 'images', 'logo-official.png')
                if os.path.exists(logo_path):
                    break
            else:
                raise FileNotFoundError("Logo file not found in STATIC_ROOT or STATICFILES_DIRS")
        logo = ImageReader(logo_path)
        c.drawImage(logo, margin, height - margin, width=100, height=50, preserveAspectRatio=True)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin + 110, height - 40, "CORPUS LEGAL PRACTITIONERS")
    except Exception as e:
        print(f"Error loading logo: {e}")
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin + 10, height - 40, "CORPUS LEGAL PRACTITIONERS")

    c.setFont("Helvetica", 10)
    c.drawRightString(width - margin, height - 60, "Piziya Office Park, Plot No. 2374")
    c.drawRightString(width - margin, height - 75, "Thabo Mbeki Road, Mass Media")
    c.drawRightString(width - margin, height - 90, "Lusaka, Zambia")
    c.drawRightString(width - margin, height - 105, "Email: corpus@corpus.co.zm")

    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width/2, height - 150, "PURCHASE ORDER")
    c.setFont("Helvetica", 10)
    c.drawRightString(width - margin, height - 170, f"PO Number: {purchase_order.purchase_order_number}")
    c.drawRightString(width - margin, height - 185, f"Date: {purchase_order.created_at.strftime('%d/%m/%Y')}")

    y = height - 220
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Supplier:")
    c.setFont("Helvetica", 10)
    c.drawString(margin + 60, y, purchase_order.destination)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y - 20, "Deliver To:")
    c.setFont("Helvetica", 10)
    c.drawString(margin + 60, y - 20, "Piziya Office Park, Thabo Mbeki Road")
    c.drawString(margin + 60, y - 35, "Mass Media, Lusaka")

    y -= 70
    table_start = y
    c.setFont("Helvetica-Bold", 10)
    c.rect(margin, y - 20, content_width, 20)
    c.drawString(margin + 5, y - 15, "Item No.")
    c.drawString(margin + 60, y - 15, "Description")
    c.drawString(margin + 300, y - 15, "Qty")
    c.drawString(margin + 350, y - 15, "Unit Price")
    c.drawString(margin + 450, y - 15, "Amount")

    c.setFont("Helvetica", 10)
    y -= 35
    for item in purchase_order.items.all():
        c.drawString(margin + 5, y, str(item.item_no))
        c.drawString(margin + 60, y, item.description[:40])
        c.drawString(margin + 300, y, str(item.quantity))
        c.drawString(margin + 350, y, f"{item.currency} {item.unit_price:,.2f}")
        c.drawString(margin + 450, y, f"{item.currency} {item.amount:,.2f}")
        y -= 20

    y -= 20
    c.setFont("Helvetica", 10)
    amount_column_x = margin + 450
    amount_column_width = 90
    label_column_x = margin + 350
    currency = purchase_order.items.first().currency if purchase_order.items.exists() else 'ZMW'
    max_num_width = max(
        len(f"{purchase_order.subtotal:,.2f}"),
        len(f"{purchase_order.vat:,.2f}") if purchase_order.include_vat else 0,
        len(f"{purchase_order.total_amount:,.2f}")
    ) * 5.5

    c.drawString(label_column_x, y, "Subtotal:")
    c.drawRightString(amount_column_x + amount_column_width - max_num_width, y, f"{currency} {purchase_order.subtotal:,.2f}")

    if purchase_order.include_vat:
        y -= 15
        c.drawString(label_column_x, y, "VAT:")
        c.drawRightString(amount_column_x + amount_column_width - max_num_width, y, f"{currency} {purchase_order.vat:,.2f}")

    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(label_column_x, y, "Total:")
    c.drawRightString(amount_column_x + amount_column_width - max_num_width, y, f"{currency} {purchase_order.total_amount:,.2f}")

    y -= 20
    c.setLineWidth(0.5)
    c.line(margin, y, margin + content_width, y)
    y -= 15

    y -= 20
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"THIS ORDER NO. {purchase_order.purchase_order_number} MUST BE QUOTED ON ALL INVOICES AND DELIVERY NOTES")

    y -= 60
    c.setFont("Helvetica", 10)
    requester_name = purchase_order.requester.get_full_name() or purchase_order.requester.username
    c.drawString(margin, y, f"Ordered By: {requester_name}")
    c.drawString(margin + 200, y, f"Department: {purchase_order.department}")
    y -= 30
    c.drawString(margin, y, "Authorized Signatures:")

    approved_signatures = [(approval.role, approval.signed_by_name) for approval in purchase_order.approvals.all() if approval.approved]
    y -= 30
    roles = [
        ("Finance Manager", margin),
        ("General Manager", margin + 200),
        ("Managing Partner", margin + 400)
    ]
    for role, x_pos in roles:
        c.setFont("Helvetica", 10)
        signed_by = next((name for r, name in approved_signatures if r == role), None)
        status = f"✓ Signed by {signed_by}" if signed_by else "__________"
        c.drawString(x_pos, y, status)
        c.drawString(x_pos, y - 15, role)

    c.setFont("Helvetica", 8)
    c.drawCentredString(width/2, margin, "This is a system-generated document. Please contact us for any discrepancies.")
    c.save()
    return f"{settings.MEDIA_URL}purchase_orders/{filename}"

def generate_petty_cash_pdf(petty_cash):
    filename = f"{petty_cash.petty_cash_number}.pdf"
    filepath = os.path.join("media/petty_cash", filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    c = canvas.Canvas(filepath, pagesize=letter)
    width, height = letter
    margin = 50

    c.setFont("Helvetica-Bold", 16)
    c.drawString(margin, height - 40, "CORPUS LEGAL PRACTITIONERS")
    c.setFont("Helvetica", 10)
    c.drawString(margin, height - 60, "Petty Cash Voucher")
    c.drawRightString(width - margin, height - 60, f"Number: {petty_cash.petty_cash_number}")
    c.drawRightString(width - margin, height - 75, f"Date: {petty_cash.date.strftime('%d/%m/%Y')}")

    y = height - 120
    requester_name = petty_cash.requester.username if petty_cash.requester else "Unknown Requester"
    c.drawString(margin, y, f"Requester: {requester_name}")
    y -= 20
    c.drawString(margin, y, f"Client: {petty_cash.client}")
    y -= 20
    c.drawString(margin, y, f"Matter ID: {petty_cash.matter_id}")
    y -= 20
    c.drawString(margin, y, f"Description: {petty_cash.description}")
    y -= 20
    c.drawString(margin, y, f"Amount: ZMW {petty_cash.amount}")

    y -= 40
    approval = petty_cash.approvals.first()
    signed_by = approval.signed_by_name if approval and approval.signed_by_name else "Pending"
    c.drawString(margin, y, f"Signed by: {signed_by}")

    c.setFont("Helvetica", 8)
    c.drawCentredString(width/2, margin, "System-generated petty cash voucher.")
    c.save()

    return f"{settings.MEDIA_URL}petty_cash/{filename}"

def home(request):
    return render(request, 'orders/create_po.html')

@login_required
def custom_logout(request):
    storage = get_messages(request)
    for message in storage:
        pass
    storage.used = True
    logout(request)
    messages.success(request, "You have been successfully logged out.")
    return redirect('account_login')