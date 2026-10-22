import smtplib
from email.message import EmailMessage
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from decimal import Decimal

from app.models.user import User
from app.models.order import Order
from app.core.config import settings
from app.core.region import format_money


class EmailService:
    """Transactional email with pluggable provider.

    Provider selection (no caller changes needed — every template method
    funnels through ``_send_email``):
      EMAIL_PROVIDER=gmail     → Gmail SMTP (free, 500/day)
      EMAIL_PROVIDER=sendgrid  → SendGrid API
      unset                    → Gmail if GMAIL_ADDRESS + GMAIL_APP_PASSWORD
                                are set, else SendGrid if its key is set.
    """

    def __init__(self):
        self.api_key = settings.SENDGRID_API_KEY
        self.from_email = settings.FROM_EMAIL
        self.client = SendGridAPIClient(self.api_key) if self.api_key else None
        self.frontend_url = settings.FRONTEND_URL
        self.gmail_address = settings.GMAIL_ADDRESS
        self.gmail_app_password = settings.GMAIL_APP_PASSWORD

        requested = (settings.EMAIL_PROVIDER or "").strip().lower() or None
        if requested in ("gmail", "sendgrid"):
            self.provider = requested
        elif self.gmail_address and self.gmail_app_password:
            self.provider = "gmail"
        elif self.api_key:
            self.provider = "sendgrid"
        else:
            self.provider = "none"

        # Debug: Check what is configured (never log secrets).
        if self.provider == "gmail":
            print(f"Email provider: Gmail SMTP (from {self.gmail_address})")
        elif self.provider == "sendgrid":
            print(f"Email provider: SendGrid (key {self.api_key[:10]}...)")
        else:
            print("WARNING: no email provider configured — emails will be skipped!")

    # ========== ✅ NEW: Public send_email method ==========
    def send_email(self, to: str, subject: str, html_body: str, plain_text: str = None) -> bool:
        """
        Public method to send emails (used by OTP service, welcome emails, etc.)
        """
        return self._send_email(
            to_email=to,
            subject=subject,
            html_content=html_body,
            plain_text=plain_text
        )

    def format_currency(self, amount: Decimal) -> str:
        from app.core.region import format_money

        return format_money(amount)

    def _send_email(self, to_email: str, subject: str, html_content: str, plain_text: str = None):
        """Internal method to send email via the configured provider."""
        if self.provider == "gmail":
            return self._send_via_gmail(to_email, subject, html_content, plain_text)
        if self.provider == "sendgrid":
            return self._send_via_sendgrid(to_email, subject, html_content, plain_text)
        print(f"No email provider configured - skipping email to {to_email}")
        return False

    def _send_via_gmail(self, to_email: str, subject: str, html_content: str, plain_text: str = None):
        """Free Gmail SMTP (500/day). Needs GMAIL_ADDRESS + App Password."""
        if not self.gmail_address or not self.gmail_app_password:
            print(f"Gmail not configured - skipping email to {to_email}")
            return False
        try:
            msg = EmailMessage()
            msg["From"] = self.gmail_address
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content(plain_text or "Please view this email in an HTML-capable client.")
            msg.add_alternative(html_content, subtype="html")
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
                smtp.login(self.gmail_address, self.gmail_app_password)
                smtp.send_message(msg)
            print(f"Email sent via Gmail to {to_email}")
            return True
        except Exception as e:
            print(f"Failed to send email via Gmail to {to_email}: {str(e)}")
            return False

    def _send_via_sendgrid(self, to_email: str, subject: str, html_content: str, plain_text: str = None):
        """SendGrid API (paid/credits)."""
        if not self.client:
            print(f"SendGrid not configured - skipping email to {to_email}")
            return False
        
        try:
            message = Mail(
                from_email=self.from_email,
                to_emails=to_email,
                subject=subject,
                html_content=html_content
            )
            if plain_text:
                message.plain_text_content = plain_text
                
            response = self.client.send(message)
            print(f"Email sent successfully to {to_email} (status: {response.status_code})")
            return response.status_code in (200, 201, 202)
        except Exception as e:
            print(f"Failed to send email to {to_email}: {str(e)}")
            return False

    def send_test_email(self, to_email: str):
        """Send a test email"""
        return self._send_email(
            to_email,
            "Test Email from E-Commerce API",
            "<h1>✅ Test Email</h1><p>If you received this, your email system is working!</p>"
        )

    # ========== Password Reset Email ==========
    def send_password_reset_email(self, user_email: str, user_name: str, reset_token: str):
        """
        Send password reset email to user.
        """
        reset_link = f"{self.frontend_url}/reset-password?token={reset_token}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                    background-color: #f6f9fc;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #ffffff;
                }}
                .header {{
                    text-align: center;
                    padding: 30px 0 20px 0;
                    border-bottom: 1px solid #e8e8e8;
                }}
                .header h1 {{
                    color: #1a1a2e;
                    font-size: 28px;
                    margin: 0;
                }}
                .header .logo {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #4f46e5;
                }}
                .content {{
                    padding: 30px 20px;
                }}
                .content p {{
                    color: #4a4a4a;
                    font-size: 16px;
                    line-height: 1.6;
                    margin: 0 0 16px 0;
                }}
                .button-container {{
                    text-align: center;
                    margin: 30px 0;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
                    color: #ffffff !important;
                    padding: 14px 40px;
                    border-radius: 8px;
                    text-decoration: none;
                    font-weight: 600;
                    font-size: 16px;
                    box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
                    transition: all 0.3s ease;
                }}
                .button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(79, 70, 229, 0.45);
                }}
                .footer {{
                    border-top: 1px solid #e8e8e8;
                    padding: 20px 20px 0 20px;
                    text-align: center;
                    color: #8c8c8c;
                    font-size: 13px;
                }}
                .footer a {{
                    color: #4f46e5;
                    text-decoration: none;
                }}
                .footer a:hover {{
                    text-decoration: underline;
                }}
                .expiry-notice {{
                    background-color: #f3f4f6;
                    padding: 12px 16px;
                    border-radius: 6px;
                    font-size: 14px;
                    color: #4b5563;
                    margin-top: 20px;
                }}
                .divider {{
                    border: none;
                    border-top: 1px solid #e5e7eb;
                    margin: 24px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <span class="logo">🛍️ E-Shop</span>
                    <h1>Reset Your Password</h1>
                </div>
                
                <div class="content">
                    <p>Hi <strong>{user_name}</strong>,</p>
                    
                    <p>We received a request to reset the password for your E-Shop account.</p>
                    
                    <p>Click the button below to create a new password:</p>
                    
                    <div class="button-container">
                        <a href="{reset_link}" class="button">Reset Password</a>
                    </div>
                    
                    <div class="expiry-notice">
                        ⏰ This link will expire in <strong>{settings.RESET_TOKEN_EXPIRE_HOURS} hour(s)</strong>.
                    </div>
                    
                    <hr class="divider">
                    
                    <p style="font-size: 14px; color: #6b7280;">
                        If you didn't request this password reset, please ignore this email. 
                        Your password will remain unchanged.
                    </p>
                    
                    <p style="font-size: 14px; color: #6b7280;">
                        For security reasons, we recommend not sharing this link with anyone.
                    </p>
                </div>
                
                <div class="footer">
                    <p>
                        <strong>E-Shop</strong><br>
                        <span style="color: #9ca3af;">Secure &bull; Reliable &bull; Trusted</span>
                    </p>
                    <p>
                        If you have any issues, contact us at 
                        <a href="mailto:{settings.FROM_EMAIL}">{settings.FROM_EMAIL}</a>
                    </p>
                    <p>&copy; {__import__('datetime').datetime.now().year} E-Shop. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        plain_text = f"""
        Reset Your Password - E-Shop
        
        Hi {user_name},
        
        We received a request to reset the password for your E-Shop account.
        
        Click the link below to reset your password:
        {reset_link}
        
        This link will expire in {settings.RESET_TOKEN_EXPIRE_HOURS} hour(s).
        
        If you didn't request this, please ignore this email.
        
        E-Shop Team
        """
        
        return self._send_email(
            to_email=user_email,
            subject="Reset Your Password - E-Shop",
            html_content=html_content,
            plain_text=plain_text
        )

    # ========== Order Emails ==========
    def send_order_confirmation(self, order: Order, user: User):
        """Send order confirmation email"""
        user = getattr(order, "customer_details", user)
        subject = f"Order Confirmed - #{order.order_number}"
        
        is_cod = (order.payment_method == "cod")
        cod_fee = order.cod_fee or Decimal("0.00")
        
        items_html = ""
        for item in order.items:
            items_html += f"""
            <tr>
                <td style="padding:10px; border-bottom:1px solid #e5e7eb;">
                    <strong>{item.product_name}</strong><br>
                    <span style="color:#6b7280; font-size:12px;">SKU: {item.variant_sku}</span>
                </td>
                <td style="padding:10px; border-bottom:1px solid #e5e7eb; text-align:center;">{item.quantity}</td>
                <td style="padding:10px; border-bottom:1px solid #e5e7eb; text-align:right;">{self.format_currency(item.unit_price)}</td>
                <td style="padding:10px; border-bottom:1px solid #e5e7eb; text-align:right;"><strong>{self.format_currency(item.line_total)}</strong></td>
            </tr>
            """
        
        # Payment-method banner
        if is_cod:
            payment_banner = f"""
            <div style="background-color:#fef3c7; border:2px solid #f59e0b; border-radius:8px; padding:16px 20px; margin:20px 0;">
                <p style="margin:0 0 6px 0; font-size:16px; font-weight:bold; color:#92400e;">
                    💵 Cash on Delivery — keep {self.format_currency(order.grand_total)} ready
                </p>
                <p style="margin:0; font-size:14px; color:#92400e;">
                    Please pay in <strong>cash</strong> when your order arrives.
                    (Includes {self.format_currency(cod_fee)} COD handling fee.)
                </p>
            </div>
            """
        else:
            payment_banner = f"""
            <div style="background-color:#dcfce7; border:2px solid #16a34a; border-radius:8px; padding:16px 20px; margin:20px 0;">
                <p style="margin:0 0 6px 0; font-size:16px; font-weight:bold; color:#166534;">
                    ✅ Payment Received — {self.format_currency(order.grand_total)}
                </p>
                <p style="margin:0; font-size:14px; color:#166534;">
                    Paid online securely. Your order is being processed.
                </p>
            </div>
            """

        cod_fee_row = ""
        if cod_fee > 0:
            cod_fee_row = f"""
                    <tr>
                        <td style="text-align:right; color:#6b7280; border-bottom:none;">COD Fee</td>
                        <td style="text-align:right; border-bottom:none; padding-left:12px;">{self.format_currency(cod_fee)}</td>
                    </tr>"""
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; background-color: #f6f9fc; margin: 0; padding: 0; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 24px; }}
                .header {{ background: #2563eb; color: white; padding: 24px 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
                th {{ padding: 10px; text-align: left; background-color: #f3f4f6; border-bottom: 2px solid #e5e7eb; font-size: 13px; text-transform: uppercase; color: #6b7280; }}
                td {{ padding: 10px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
                .meta {{ color: #374151; font-size: 14px; margin: 6px 0; }}
                .footer {{ margin-top: 24px; padding: 20px; text-align: center; color: #9ca3af; font-size: 12px; border-top: 1px solid #e5e7eb; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin:0;">Thank You for Your Order! 🎉</h1>
                </div>

                {payment_banner}

                <p class="meta"><strong>Order Number:</strong> #{order.order_number}</p>
                <p class="meta"><strong>Order Date:</strong> {order.placed_at.strftime('%B %d, %Y')}</p>
                <p class="meta"><strong>Payment Method:</strong> {'💵 Cash on Delivery' if is_cod else '💳 Paid Online'}</p>
                
                <h3>Order Items</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th style="text-align:center;">Qty</th>
                            <th style="text-align:right;">Price</th>
                            <th style="text-align:right;">Total</th>
                        </tr>
                    </thead>
                    <tbody>{items_html}</tbody>
                </table>
                
                <h3>Order Summary</h3>
                <table>
                    <tr>
                        <td style="text-align:right; color:#6b7280; border-bottom:none;">Subtotal</td>
                        <td style="text-align:right; border-bottom:none; padding-left:12px;">{self.format_currency(order.subtotal)}</td>
                    </tr>
                    <tr>
                        <td style="text-align:right; color:#6b7280; border-bottom:none;">Discount</td>
                        <td style="text-align:right; border-bottom:none; padding-left:12px;">-{self.format_currency(order.discount_total)}</td>
                    </tr>
                    <tr>
                        <td style="text-align:right; color:#6b7280; border-bottom:none;">Tax</td>
                        <td style="text-align:right; border-bottom:none; padding-left:12px;">{self.format_currency(order.tax_total)}</td>
                    </tr>
                    <tr>
                        <td style="text-align:right; color:#6b7280; border-bottom:none;">Shipping</td>
                        <td style="text-align:right; border-bottom:none; padding-left:12px;">{self.format_currency(order.shipping_total)}</td>
                    </tr>{cod_fee_row}
                    <tr>
                        <td style="text-align:right; font-size:18px; font-weight:bold; color:#2563eb; border-top:2px solid #2563eb;">Grand Total</td>
                        <td style="text-align:right; font-size:18px; font-weight:bold; color:#2563eb; border-top:2px solid #2563eb; padding-left:12px;">{self.format_currency(order.grand_total)}</td>
                    </tr>
                </table>
                
                <div class="footer">
                    <p>Thank you for shopping with us!</p>
                    <p>Questions about your order? Contact us at {settings.FROM_EMAIL}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        self._send_email(user.email, subject, html_content)

    def send_order_shipped(self, order: Order, user: User):
        """Send order shipped notification"""
        user = getattr(order, "customer_details", user)
        subject = f"Your Order Has Been Shipped - #{order.order_number}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #16a34a; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📦 Your Order is On Its Way!</h1>
            </div>
            
            <p>Hi {user.full_name or 'Customer'},</p>
            <p>Your order <strong>#{order.order_number}</strong> has been shipped!</p>
            <p><strong>Total:</strong> {self.format_currency(order.grand_total)}</p>
            
            <div class="footer">
                <p>Thank you for shopping with us!</p>
            </div>
        </body>
        </html>
        """
        self._send_email(user.email, subject, html_content)

    def send_order_delivered(self, order: Order, user: User):
        """Send order delivered notification"""
        user = getattr(order, "customer_details", user)
        subject = f"Your Order Has Been Delivered - #{order.order_number}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #16a34a; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>✅ Order Delivered!</h1>
            </div>
            
            <p>Hi {user.full_name or 'Customer'},</p>
            <p>Your order <strong>#{order.order_number}</strong> has been delivered! 🎉</p>
            <p><strong>Total:</strong> {self.format_currency(order.grand_total)}</p>
            
            <div class="footer">
                <p>Thank you for shopping with us!</p>
            </div>
        </body>
        </html>
        """
        self._send_email(user.email, subject, html_content)

    def send_order_cancelled(self, order: Order, user: User):
        """Send order cancelled notification"""
        user = getattr(order, "customer_details", user)
        subject = f"Order Cancelled - #{order.order_number}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #dc2626; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Order Cancelled ❌</h1>
            </div>
            
            <p>Hi {user.full_name or 'Customer'},</p>
            <p>Your order <strong>#{order.order_number}</strong> has been cancelled.</p>
            <p><strong>Order Date:</strong> {order.placed_at.strftime('%B %d, %Y')}</p>
            <p><strong>Total:</strong> {self.format_currency(order.grand_total)}</p>
            
            <p>If you have any questions, please contact our support team.</p>
            
            <div class="footer">
                <p>Thank you for shopping with us!</p>
            </div>
        </body>
        </html>
        """
        self._send_email(user.email, subject, html_content)

    def send_order_refunded(self, order: Order, user: User):
        """Send order refunded notification"""
        user = getattr(order, "customer_details", user)
        subject = f"Refund Initiated - #{order.order_number}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #f59e0b; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Refund Initiated 💰</h1>
            </div>
            
            <p>Hi {user.full_name or 'Customer'},</p>
            <p>A refund for order <strong>#{order.order_number}</strong> has been initiated.</p>
            <p><strong>Order Date:</strong> {order.placed_at.strftime('%B %d, %Y')}</p>
            <p><strong>Refund Amount:</strong> {self.format_currency(order.refund_amount or order.grand_total)}</p>
            
            <p>The refund will reflect in your account within 3-5 business days.</p>
            <p>If you have any questions, please contact our support team.</p>
            
            <div class="footer">
                <p>Thank you for shopping with us!</p>
            </div>
        </body>
        </html>
        """
        self._send_email(user.email, subject, html_content)

    def send_refund_approval_needed(
        self, to_email: str, to_name: str, order_number: str,
        amount, requester: str, reason: str | None,
    ):
        """Tell an eligible approver a refund awaits their decision."""
        subject = f"Refund approval needed — Order #{order_number} ({format_money(amount)})"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #d97706; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Refund Approval Needed</h1>
            </div>

            <p>Hi {to_name or 'Admin'},</p>
            <p><strong>{requester}</strong> requested a refund of
            <strong>{format_money(amount)}</strong> on order <strong>#{order_number}</strong>.</p>
            <p><strong>Reason:</strong> {reason or '—'}</p>

            <p>Review it in the admin panel under <strong>Refunds → Pending approval</strong>.
            No money moves until a different admin approves.</p>

            <div class="footer">
                <p>This is an automated alert. Please do not reply.</p>
            </div>
        </body>
        </html>
        """
        self._send_email(to_email, subject, html_content)

    def send_refund_completed(self, order: Order, user: User):
        user = getattr(order, "customer_details", user)
        """Send refund completed notification"""
        subject = f"Refund Completed - #{order.order_number}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #16a34a; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Refund Completed ✅</h1>
            </div>

            <p>Hi {user.full_name or 'Customer'},</p>
            <p>Good news! The refund for your order <strong>#{order.order_number}</strong> has been completed.</p>
            <p><strong>Refund Amount:</strong> {self.format_currency(order.refund_amount or order.grand_total)}</p>
            <p><strong>Refund ID:</strong> {order.refund_id or '-'}</p>

            <p>The money has been credited back to your original payment method. It may take 1-2 days to reflect in your bank account.</p>
            <p>If you have any questions, please contact our support team.</p>

            <div class="footer">
                <p>Thank you for shopping with us!</p>
            </div>
        </body>
        </html>
        """
        self._send_email(user.email, subject, html_content)

    def send_refund_failed(self, order: Order, user: User):
        user = getattr(order, "customer_details", user)
        """Send refund failed notification"""
        subject = f"Refund Issue - #{order.order_number}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #dc2626; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Refund Failed ❌</h1>
            </div>

            <p>Hi {user.full_name or 'Customer'},</p>
            <p>We're sorry, but the refund for your order <strong>#{order.order_number}</strong> could not be processed.</p>
            <p><strong>Refund Amount:</strong> {self.format_currency(order.refund_amount or order.grand_total)}</p>
            <p><strong>Refund ID:</strong> {order.refund_id or '-'}</p>

            <p>Please contact our support team for assistance and we will resolve this at the earliest.</p>

            <div class="footer">
                <p>Thank you for shopping with us!</p>
            </div>
        </body>
        </html>
        """
        self._send_email(user.email, subject, html_content)

    def send_welcome_email(self, user: User):
        """Send welcome email"""
        subject = f"Welcome to Our Store, {user.full_name or user.username}!"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Welcome to Our Store! 🎉</h1>
            </div>
            
            <p>Hi {user.full_name or user.username},</p>
            <p>Thank you for joining us! We're excited to have you as a customer.</p>
            
            <p>Here's what you can do:</p>
            <ul>
                <li>🛍️ Browse our products</li>
                <li>❤️ Save items to your wishlist</li>
                <li>📦 Track your orders</li>
            </ul>
            
            <p>Start shopping now!</p>
            
            <div class="footer">
                <p>If you have any questions, feel free to reach out!</p>
            </div>
        </body>
        </html>
        """
        self._send_email(user.email, subject, html_content)

    def send_promotion_email(
        self,
        to_email: str,
        to_name: str | None,
        title: str,
        message: str,
        link: str | None = None,
    ) -> bool:
        """Send one promotional email (bulk fan-out calls this per recipient).

        Promotional mail is consent-gated by the caller on
        ``User.email_notifications_enabled`` — this method sends blindly.
        """
        name = (to_name or "").strip() or "there"
        cta = ""
        if (link or "").strip():
            cta = f"""
            <p style="text-align: center; margin: 24px 0;">
                <a href="{link.strip()}"
                   style="display: inline-block; background: #2563eb; color: white;
                          padding: 12px 28px; text-decoration: none; border-radius: 6px;
                          font-weight: bold;">Shop Now</a>
            </p>"""
        subject = title.strip()
        plain_text = (
            f"Hi {name},\n\n{title.strip()}\n\n{message.strip()}\n"
            + (f"\nShop now: {link.strip()}\n" if (link or "").strip() else "")
            + "\nYou received this because Email Notifications are on in your "
              "account. Turn them off anytime under Settings → Notifications."
        )
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .header {{ background: #2563eb; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .footer {{ margin-top: 20px; padding: 20px; text-align: center; color: #888; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📣 {title.strip()}</h1>
            </div>
            <div class="content">
                <p>Hi {name},</p>
                <p>{message.strip()}</p>
                {cta}
            </div>
            <div class="footer">
                <p>You received this because Email Notifications are on in your account.</p>
                <p>Turn them off anytime under Settings → Notifications.</p>
            </div>
        </body>
        </html>
        """
        return self._send_email(to_email, subject, html_content, plain_text)


# Singleton instance
email_service = EmailService()
