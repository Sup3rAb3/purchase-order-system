from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from orders.models import SignatoryApproval, PurchaseOrder
from orders.utils import get_approvers_for_amount
from datetime import timedelta

class Command(BaseCommand):
    help = 'Check for approval requests that have timed out and resend to fallbacks'

    def handle(self, *args, **kwargs):
        pending_approvals = SignatoryApproval.objects.filter(
            approved__isnull=True,
            purchase_order__status="Pending",
            purchase_order__isnull=False
        )
        self.stdout.write(self.style.SUCCESS(f"Found {pending_approvals.count()} pending approvals"))

        for approval in pending_approvals:
            self.stdout.write(self.style.SUCCESS(f"Processing approval for PO {approval.purchase_order.purchase_order_number} by {approval.approver.role if approval.approver else 'None'}"))
            if not approval.approver or not approval.last_email_sent:
                self.stdout.write(self.style.WARNING(f"Skipping due to missing approver or last_email_sent for PO {approval.purchase_order.purchase_order_number}"))
                continue

            time_elapsed = timezone.now() - approval.last_email_sent
            self.stdout.write(self.style.SUCCESS(f"Time elapsed for PO {approval.purchase_order.purchase_order_number}: {time_elapsed}"))
            self.stdout.write(self.style.SUCCESS(f"Availability timeout: {approval.availability_timeout}"))
            if time_elapsed > approval.availability_timeout:
                self.stdout.write(self.style.SUCCESS(f"Timeout detected for PO {approval.purchase_order.purchase_order_number}"))
                approval.approver.is_available = False
                approval.approver.save()

                if approval.purchase_order.requester.email:
                    send_mail(
                        f"Approver Unavailable for PO {approval.purchase_order.purchase_order_number}",
                        f"{approval.approver.role} did not respond; the request has been sent to their fallback.",
                        'amanda@corpus.co.zm',
                        [approval.purchase_order.requester.email],
                        fail_silently=False,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Notification sent to requester for PO {approval.purchase_order.purchase_order_number}"))

                if approval.approver.fallback_approver:
                    self.stdout.write(self.style.SUCCESS(f"Escalating to fallback {approval.approver.fallback_approver.role} for PO {approval.purchase_order.purchase_order_number}"))
                    new_approval = SignatoryApproval.objects.create(
                        purchase_order=approval.purchase_order,
                        approver=approval.approver.fallback_approver,
                        role=approval.approver.fallback_approver.role,
                        on_behalf_of=approval,  # Changed from approval.approver to approval
                        last_email_sent=timezone.now(),
                        availability_timeout=timedelta(hours=24)
                    )
                    new_approval.send_approval_email()
                    self.stdout.write(self.style.SUCCESS(f"New approval created and email sent for PO {approval.purchase_order.purchase_order_number}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"No fallback approver for PO {approval.purchase_order.purchase_order_number}"))
                    po = approval.purchase_order
                    required_approvers = get_approvers_for_amount(po)
                    all_approvals = po.approvals.all()
                    all_timed_out = True
                    for req_approver in required_approvers:
                        approver_approvals = [a for a in all_approvals if a.approver == req_approver or a.on_behalf_of == req_approver]
                        if any(a.approved is not None for a in approver_approvals):
                            all_timed_out = False
                            break
                    if all_timed_out:
                        po.status = "Rejected"
                        po.save()
                        rejection_approval = SignatoryApproval.objects.create(
                            purchase_order=po,
                            role="System",
                            approved=False,
                            signed_by_name="System (timeout)"
                        )
                        rejection_approval.send_final_decision_email("rejected")
                        self.stdout.write(self.style.SUCCESS(f"PO {po.purchase_order_number} rejected due to all timeouts"))

        self.stdout.write(self.style.SUCCESS('Checked approval timeouts and resent to fallbacks'))