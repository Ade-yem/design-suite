"""
services/email.py
=================
Transactional email service driven by Resend.

Provides asynchronous dispatch of onboarding and security emails
(Welcome, Verification, Password Reset, and 2FA OTP codes) using
``asyncio.to_thread`` to keep the FastAPI event loop fully non-blocking.

Includes a developer-friendly fallback to print email details to the
logs when no RESEND_API_KEY is configured in the environment.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any

import resend

from config import settings

logger = logging.getLogger(__name__)

# Initialise resend library
resend.api_key = settings.RESEND_API_KEY


class EmailService:
    """
    Service responsible for dispatching system emails via Resend.

    Uses non-blocking thread execution to prevent SMTP/HTTP network latency
    from delaying main API event handlers.
    """

    def __init__(self) -> None:
        """
        Initialise EmailService. Sets up the sender context from configuration.
        """
        self.sender = settings.SENDER_EMAIL or "onboarding@resend.dev"

    async def _send_html_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
    ) -> None:
        """
        Internal worker that dispatches the HTML payload using Resend.

        If RESEND_API_KEY is unset or contains placeholders, falls back to logging.

        Parameters
        ----------
        to_email : str
            Recipient email address.
        subject : str
            Email subject line.
        html_content : str
            Complete HTML string to transmit.
        """
        if not settings.RESEND_API_KEY or "change-me" in settings.RESEND_API_KEY or not settings.RESEND_API_KEY.strip():
            logger.warning(
                "[DEVELOPMENT MODE] Email not sent via Resend (API key missing/default).\n"
                "----------------------------------------\n"
                "To      : %s\n"
                "From    : %s\n"
                "Subject : %s\n"
                "Content :\n%s\n"
                "----------------------------------------",
                to_email,
                self.sender,
                subject,
                html_content,
            )
            return

        try:
            params: Dict[str, Any] = {
                "from": self.sender,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }
            # Execute synchronous Resend SDK call in a separate worker thread
            # pyrefly: ignore [bad-argument-type]
            await asyncio.to_thread(resend.Emails.send, params)
            logger.info("Successfully dispatched email to %s (Subject: '%s').", to_email, subject)
        except Exception as e:
            logger.error("Failed to send email to %s via Resend: %s", to_email, str(e), exc_info=True)
            # Do not crash the auth process if the email service fails (resiliency guard)
            pass

    async def send_welcome_email(
        self,
        to_email: str,
        name: str,
    ) -> None:
        """
        Send a beautiful welcome email to newly registered users.

        Parameters
        ----------
        to_email : str
            User's email.
        name : str
            Display name of the user.
        """
        subject = "Welcome to Structural Design Copilot!"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{subject}</title>
            <style>
                body {{
                    font-family: 'Inter', -apple-system, sans-serif;
                    background-color: #0f172a;
                    color: #f1f5f9;
                    margin: 0;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #1e293b;
                    border-radius: 12px;
                    padding: 40px;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                    border: 1px solid #334155;
                }}
                h1 {{
                    color: #38bdf8;
                    font-size: 24px;
                    margin-bottom: 20px;
                }}
                p {{
                    font-size: 16px;
                    line-height: 1.6;
                    color: #cbd5e1;
                }}
                .btn {{
                    display: inline-block;
                    background-color: #0284c7;
                    color: #ffffff !important;
                    text-decoration: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-weight: 600;
                    margin-top: 20px;
                }}
                .footer {{
                    margin-top: 40px;
                    font-size: 12px;
                    color: #64748b;
                    border-top: 1px solid #334155;
                    padding-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Welcome, {name}! 🚀</h1>
                <p>Thank you for registering at <strong>Structural Design Copilot</strong>.</p>
                <p>Our AI-driven multi-agent platform enables engineers to automate transition stages from DXF drawings to reinforced concrete designs seamlessly while retaining strict human-in-the-loop validation.</p>
                <p>To get started, log into the workspace and explore the Side-by-Side Interactive Canvas and Copilot Chat panels.</p>
                <a href="http://localhost:5173/login" class="btn">Access the Workspace</a>
                <div class="footer">
                    <p>This is an automated operational transmission. Please do not reply directly to this address.</p>
                </div>
            </div>
        </body>
        </html>
        """
        await self._send_html_email(to_email, subject, html_content)

    async def send_verification_email(
        self,
        to_email: str,
        token: str,
    ) -> None:
        """
        Send a verification email with a token link to allow a user to verify their account.

        Parameters
        ----------
        to_email : str
            User's email.
        token : str
            FastAPIUsers signed verification token.
        """
        subject = "Verify Your Account - Structural Design Copilot"
        # In production, point this link to your frontend verification route
        verify_url = f"{settings.FRONTEND_URL}/verify?token={token}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{subject}</title>
            <style>
                body {{
                    font-family: 'Inter', -apple-system, sans-serif;
                    background-color: #0f172a;
                    color: #f1f5f9;
                    margin: 0;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #1e293b;
                    border-radius: 12px;
                    padding: 40px;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                    border: 1px solid #334155;
                }}
                h1 {{
                    color: #38bdf8;
                    font-size: 24px;
                    margin-bottom: 20px;
                }}
                p {{
                    font-size: 16px;
                    line-height: 1.6;
                    color: #cbd5e1;
                }}
                .btn {{
                    display: inline-block;
                    background-color: #10b981;
                    color: #ffffff !important;
                    text-decoration: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-weight: 600;
                    margin-top: 20px;
                }}
                .footer {{
                    margin-top: 40px;
                    font-size: 12px;
                    color: #64748b;
                    border-top: 1px solid #334155;
                    padding-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Verify Your Identity 🛡️</h1>
                <p>You have registered an account on Structural Design Copilot. To activate your account and log into the IDE, please verify your email address.</p>
                <p>Click the button below to confirm your registration. This verification link will expire in 24 hours.</p>
                <a href="{verify_url}" class="btn">Verify Email Address</a>
                <p style="margin-top: 20px; font-size: 14px; color: #94a3b8;">
                    If the button doesn't work, copy and paste the following link into your browser:<br>
                    <a href="{verify_url}" style="color: #38bdf8; word-break: break-all;">{verify_url}</a>
                </p>
                <div class="footer">
                    <p>If you did not request this account creation, please ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        await self._send_html_email(to_email, subject, html_content)

    async def send_reset_password_email(
        self,
        to_email: str,
        token: str,
    ) -> None:
        """
        Send a password reset link to an email/password-registered user.

        Parameters
        ----------
        to_email : str
            User's email.
        token : str
            FastAPIUsers signed password reset token.
        """
        subject = "Reset Your Password - Structural Design Copilot"
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{subject}</title>
            <style>
                body {{
                    font-family: 'Inter', -apple-system, sans-serif;
                    background-color: #0f172a;
                    color: #f1f5f9;
                    margin: 0;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #1e293b;
                    border-radius: 12px;
                    padding: 40px;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                    border: 1px solid #334155;
                }}
                h1 {{
                    color: #f43f5e;
                    font-size: 24px;
                    margin-bottom: 20px;
                }}
                p {{
                    font-size: 16px;
                    line-height: 1.6;
                    color: #cbd5e1;
                }}
                .btn {{
                    display: inline-block;
                    background-color: #f43f5e;
                    color: #ffffff !important;
                    text-decoration: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-weight: 600;
                    margin-top: 20px;
                }}
                .footer {{
                    margin-top: 40px;
                    font-size: 12px;
                    color: #64748b;
                    border-top: 1px solid #334155;
                    padding-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Reset Your Password 🔑</h1>
                <p>A password reset request was received for your Structural Design Copilot account.</p>
                <p>Please click the button below to choose a new password. This reset link will expire in 2 hours.</p>
                <a href="{reset_url}" class="btn">Reset Password</a>
                <p style="margin-top: 20px; font-size: 14px; color: #94a3b8;">
                    If the button doesn't work, copy and paste the following link into your browser:<br>
                    <a href="{reset_url}" style="color: #f43f5e; word-break: break-all;">{reset_url}</a>
                </p>
                <div class="footer">
                    <p>If you did not make this request, your password remains secure, and you can safely ignore this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        await self._send_html_email(to_email, subject, html_content)

    async def send_2fa_code_email(
        self,
        to_email: str,
        code: str,
    ) -> None:
        """
        Send a transient 6-digit 2FA verification PIN for logging in.

        Parameters
        ----------
        to_email : str
            User's email.
        code : str
            6-digit verification pin code.
        """
        subject = "Your 2-Factor Authentication Code"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{subject}</title>
            <style>
                body {{
                    font-family: 'Inter', -apple-system, sans-serif;
                    background-color: #0f172a;
                    color: #f1f5f9;
                    margin: 0;
                    padding: 40px 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: #1e293b;
                    border-radius: 12px;
                    padding: 40px;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
                    border: 1px solid #334155;
                    text-align: center;
                }}
                h1 {{
                    color: #38bdf8;
                    font-size: 24px;
                    margin-bottom: 20px;
                }}
                p {{
                    font-size: 16px;
                    line-height: 1.6;
                    color: #cbd5e1;
                }}
                .code-box {{
                    display: inline-block;
                    font-size: 32px;
                    font-weight: 700;
                    letter-spacing: 6px;
                    color: #ffffff;
                    background-color: #0f172a;
                    border: 2px dashed #0284c7;
                    padding: 16px 32px;
                    border-radius: 8px;
                    margin: 24px 0;
                }}
                .warning {{
                    font-size: 13px;
                    color: #94a3b8;
                    margin-top: 16px;
                }}
                .footer {{
                    margin-top: 40px;
                    font-size: 12px;
                    color: #64748b;
                    border-top: 1px solid #334155;
                    padding-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Verify Your Session 🔐</h1>
                <p>A login request was made for your account that requires verification.</p>
                <p>Use the following 6-digit verification code to complete your access validation. This code is valid for <strong>5 minutes</strong>.</p>
                <div class="code-box">{code}</div>
                <p class="warning">Do not share this code with anyone. Employees of Structural Design Copilot will never ask for this code.</p>
                <div class="footer">
                    <p>If you did not initiate this login request, please secure your account immediately by changing your password.</p>
                </div>
            </div>
        </body>
        </html>
        """
        await self._send_html_email(to_email, subject, html_content)


# Single shared instance across application contexts
email_service = EmailService()
