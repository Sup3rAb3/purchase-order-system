from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from orders.models import ApprovalThreshold, Approver, SignatoryApproval, PurchaseOrder

def get_approvers_for_amount(purchase_order):
    """
    Determine the list of approvers for a given PurchaseOrder based on its total amount in ZMW and department.
    Returns a list of Approver objects.
    """
    try:
        amount_in_zmw = purchase_order.total_amount_in_zmw()
        department = purchase_order.department

        # Find the threshold for the department
        threshold = ApprovalThreshold.objects.filter(
            department=department,
            min_amount_zmw__lte=amount_in_zmw
        ).filter(
            Q(max_amount_zmw__gte=amount_in_zmw) | Q(max_amount_zmw__isnull=True)
        ).first()

        if not threshold:
            # If no threshold matches (e.g., amount below the minimum threshold), return empty list
            return []

        # Return the primary approvers
        return list(threshold.approvers.all())
    except ObjectDoesNotExist as e:
        raise ValueError(f"Error determining approvers: {str(e)}")

def request_approval(purchase_order):
    """
    Handle the approval request logic for a given PurchaseOrder.
    Returns a tuple: (success: bool, message: str)
    """
    try:
        approvers = get_approvers_for_amount(purchase_order)
        if not approvers:
            return True, "Your purchase order has been successfully submitted! No approvers required."

        approvals = []
        for approver in approvers:
            approval = SignatoryApproval.objects.create(
                purchase_order=purchase_order,
                approver=approver,
                role=approver.role,
                last_email_sent=timezone.now(),
                availability_timeout=timezone.timedelta(hours=24)
            )
            try:
                approval.send_approval_email()
            except Exception as e:
                return False, f"Failed to send approval email to {approver.email}: {str(e)}"
            approvals.append(approval)

        return True, "Your purchase order has been successfully submitted! Approval emails have been sent."
    except Exception as e:
        return False, f"Error processing approval request: {str(e)}"