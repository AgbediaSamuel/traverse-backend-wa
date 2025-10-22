"""Email service using Resend API."""

import os
from typing import List, Optional

import resend
from dotenv import load_dotenv

load_dotenv()

# Initialize Resend with API key
resend.api_key = os.getenv("RESEND_API_KEY", "")


class EmailService:
    """Service for sending emails via Resend."""

    def __init__(self, api_key: Optional[str] = None, sender_email: Optional[str] = None):
        """
        Initialize email service with optional API key override.

        Args:
            api_key: Resend API key (defaults to RESEND_API_KEY env var)
            sender_email: Sender email address (defaults to RESEND_SENDER_EMAIL env var or onboarding@resend.dev for testing)
        """
        if api_key:
            resend.api_key = api_key

        # Use provided sender email, or fall back to env var, or use Resend's test domain
        self.sender_email = sender_email or os.getenv(
            "RESEND_SENDER_EMAIL", "onboarding@resend.dev"
        )

    def send_trip_invite(
        self,
        recipient_email: str,
        recipient_name: str,
        organizer_name: str,
        trip_name: str,
        destination: Optional[str] = None,
        date_range_start: Optional[str] = None,
        date_range_end: Optional[str] = None,
        custom_message: Optional[str] = None,
        invite_link: str = "",
    ) -> bool:
        """
        Send a trip invite email to a participant.

        Args:
            recipient_email: Email address of the participant
            recipient_name: Full name of the participant
            organizer_name: Name of the trip organizer
            trip_name: Name of the trip
            destination: Trip destination (optional)
            date_range_start: Start date of the trip (optional)
            date_range_end: End date of the trip (optional)
            custom_message: Custom message from organizer (optional)
            invite_link: Link to respond to the invite

        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            # Build the email HTML content
            html_content = self._build_invite_email_html(
                recipient_name=recipient_name,
                organizer_name=organizer_name,
                trip_name=trip_name,
                destination=destination,
                date_range_start=date_range_start,
                date_range_end=date_range_end,
                custom_message=custom_message,
                invite_link=invite_link,
            )

            # Send email via Resend
            params = {
                "from": f"Traverse <{self.sender_email}>",
                "to": [recipient_email],
                "subject": f"🌍 You're invited to {trip_name}!",
                "html": html_content,
            }

            response = resend.Emails.send(params)
            print(f"[Email] Sent invite to {recipient_email}: {response}")
            return True

        except Exception as e:
            print(f"[Email] Error sending invite to {recipient_email}: {e}")
            return False

    def send_itinerary_share(
        self,
        recipient_email: str,
        recipient_name: str,
        organizer_name: str,
        destination: str,
        dates: str,
        duration: str,
        itinerary_link: str,
    ) -> bool:
        """
        Send an email to share a completed itinerary with a group member.

        Args:
            recipient_email: Email address of the participant
            recipient_name: Full name of the participant
            organizer_name: Name of the trip organizer
            destination: Trip destination
            dates: Trip dates
            duration: Trip duration
            itinerary_link: Link to view the itinerary

        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <div style="text-align: center; padding: 20px 0;">
                            <h1 style="color: #a1f800; margin: 0;">🌍 Traverse</h1>
                        </div>
                        
                        <h2 style="color: #333;">Hey {recipient_name}!</h2>
                        <p><strong>{organizer_name}</strong> has created an itinerary for your group trip and wants to share it with you:</p>
                        
                        <div style="background-color: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
                            <h3 style="margin-top: 0; color: #333;">{destination}</h3>
                            <p style="margin: 10px 0;"><strong>📅 Dates:</strong> {dates}</p>
                            <p style="margin: 10px 0;"><strong>⏱️ Duration:</strong> {duration}</p>
                        </div>

                        <p>Click the button below to view your complete itinerary:</p>
                        
                        <div style="margin: 30px 0; text-align: center;">
                            <a href="{itinerary_link}" style="background-color: #a1f800; color: black; padding: 15px 40px; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 16px; display: inline-block;">
                                View Itinerary
                            </a>
                        </div>

                        <p style="color: #666; font-size: 14px;">
                            Get ready for an amazing adventure! 🎉
                        </p>

                        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                        
                        <p style="color: #999; font-size: 12px; text-align: center;">
                            This itinerary was shared via Traverse - Your AI Travel Companion<br>
                            If you received this email by mistake, you can safely ignore it.
                        </p>
                    </div>
                </body>
            </html>
            """

            params = {
                "from": f"Traverse <{self.sender_email}>",
                "to": [recipient_email],
                "subject": f"🗺️ Your itinerary for {destination} is ready!",
                "html": html_content,
            }

            response = resend.Emails.send(params)
            print(f"[Email] Sent itinerary share to {recipient_email}: {response}")
            return True

        except Exception as e:
            print(f"[Email] Error sending itinerary share to {recipient_email}: {e}")
            return False

    def send_preferences_reminder(
        self,
        recipient_email: str,
        recipient_name: str,
        organizer_name: str,
        trip_name: str,
        preferences_link: str,
    ) -> bool:
        """
        Send a reminder email to complete preferences.

        Args:
            recipient_email: Email address of the participant
            recipient_name: Full name of the participant
            organizer_name: Name of the trip organizer
            trip_name: Name of the trip
            preferences_link: Link to complete preferences

        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            html_content = f"""
            <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #a1f800;">Hey {recipient_name}!</h2>
                        <p>This is a friendly reminder from {organizer_name} to complete your travel preferences for <strong>{trip_name}</strong>.</p>
                        <p>Your input will help create the perfect itinerary for everyone!</p>
                        <div style="margin: 30px 0; text-align: center;">
                            <a href="{preferences_link}" style="background-color: #a1f800; color: black; padding: 12px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
                                Complete Preferences
                            </a>
                        </div>
                        <p style="color: #666; font-size: 14px;">
                            If you have any questions, reach out to {organizer_name}.
                        </p>
                        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                        <p style="color: #999; font-size: 12px; text-align: center;">
                            Sent by Traverse - Your AI Travel Companion
                        </p>
                    </div>
                </body>
            </html>
            """

            params = {
                "from": f"Traverse <{self.sender_email}>",
                "to": [recipient_email],
                "subject": f"⏰ Don't forget to set your preferences for {trip_name}",
                "html": html_content,
            }

            response = resend.Emails.send(params)
            print(f"[Email] Sent preferences reminder to {recipient_email}: {response}")
            return True

        except Exception as e:
            print(f"[Email] Error sending preferences reminder to {recipient_email}: {e}")
            return False

    def _build_invite_email_html(
        self,
        recipient_name: str,
        organizer_name: str,
        trip_name: str,
        destination: Optional[str],
        date_range_start: Optional[str],
        date_range_end: Optional[str],
        custom_message: Optional[str],
        invite_link: str,
    ) -> str:
        """Build the HTML content for the trip invite email."""

        # Build date range string
        date_info = ""
        if date_range_start and date_range_end:
            date_info = f"<p><strong>📅 Dates:</strong> {date_range_start} to {date_range_end}</p>"
        elif date_range_start:
            date_info = f"<p><strong>📅 Starting:</strong> {date_range_start}</p>"

        # Build destination info
        destination_info = ""
        if destination:
            destination_info = f"<p><strong>📍 Destination:</strong> {destination}</p>"

        # Build custom message
        message_section = ""
        if custom_message:
            message_section = f"""
            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 0; font-style: italic;">"{custom_message}"</p>
                <p style="margin: 10px 0 0 0; color: #666; font-size: 14px;">- {organizer_name}</p>
            </div>
            """

        html = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="text-align: center; padding: 20px 0;">
                        <h1 style="color: #a1f800; margin: 0;">🌍 Traverse</h1>
                    </div>
                    
                    <h2 style="color: #333;">Hey {recipient_name}!</h2>
                    <p><strong>{organizer_name}</strong> has invited you to join them on an exciting trip:</p>
                    
                    <div style="background-color: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #333;">{trip_name}</h3>
                        {destination_info}
                        {date_info}
                    </div>

                    {message_section}

                    <p>Click the button below to view the invite and share your availability:</p>
                    
                    <div style="margin: 30px 0; text-align: center;">
                        <a href="{invite_link}" style="background-color: #a1f800; color: black; padding: 15px 40px; text-decoration: none; border-radius: 10px; font-weight: bold; font-size: 16px; display: inline-block;">
                            View Invite & Respond
                        </a>
                    </div>

                    <p style="color: #666; font-size: 14px;">
                        Looking forward to planning an amazing trip together! 🎉
                    </p>

                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    
                    <p style="color: #999; font-size: 12px; text-align: center;">
                        This invitation was sent via Traverse - Your AI Travel Companion<br>
                        If you received this email by mistake, you can safely ignore it.
                    </p>
                </div>
            </body>
        </html>
        """

        return html


# Singleton instance
email_service = EmailService()
