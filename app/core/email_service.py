"""Email service using Resend API."""

import logging
import os
from typing import Optional

import resend
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Initialize Resend with API key
resend.api_key = os.getenv("RESEND_API_KEY", "")


class EmailService:
    """Service for sending emails via Resend."""

    def __init__(
        self, api_key: Optional[str] = None, sender_email: Optional[str] = None
    ):
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
                "from": "Traverse <app@traverse-hq.com>",
                "to": [recipient_email],
                "subject": (
                    f"{organizer_name} invited you to plan your next trip "
                    "on Traverse ✈️"
                ),
                "html": html_content,
            }

            response = resend.Emails.send(params)
            logger.info(f"Sent invite to {recipient_email}: {response}")
            return True

        except Exception as e:
            logger.error(f"Error sending invite to {recipient_email}: {e}")
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
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
                </head>
                <body style="margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #ffffff;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 30px 20px;">
                        <h2 style="color: #333; font-family: 'Montserrat', Arial, sans-serif;">Hey {recipient_name}!</h2>
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
            logger.info(f"Sent itinerary share to {recipient_email}: {response}")
            return True

        except Exception as e:
            logger.error(f"Error sending itinerary share to {recipient_email}: {e}")
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

        # Extract first name from recipient_name (fallback to full name if parsing fails)
        first_name = (
            recipient_name.split()[0] if recipient_name.split() else recipient_name
        )

        # Inline SVG arrow icon (Lucide-style) - two versions for different contexts
        arrow_icon_inline = """
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-left: 4px; display: inline-block;">
            <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
        """

        arrow_icon_button = """
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-left: 6px; display: inline-block;">
            <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
        """

        html = f"""
        <!DOCTYPE html>
        <html>
            <head>
                <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
            </head>
            <body style="margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #ffffff;">
                <div style="max-width: 600px; margin: 0 auto; padding: 30px 20px;">
                    <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">Hi {first_name},</p>
                    
                    <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">
                        <strong style="font-weight: 600;">{organizer_name}</strong> just started a trip — <strong style="font-weight: 600;">"{trip_name}"</strong> — and wants you in.
                    </p>
                    
                    <p style="font-size: 16px; color: #333; margin: 0 0 24px 0; font-family: 'Montserrat', Arial, sans-serif;">
                        <span style="display: inline-block; vertical-align: middle; margin-right: 8px;">{arrow_icon_inline}</span>Tap below to <strong style="font-weight: 600;">add your available dates</strong> and help the group lock in the trip:
                    </p>
                    
                    <div style="margin: 32px 0; text-align: center;">
                        <a href="{invite_link}" style="background-color: #a1f800; color: #000000; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 16px; display: inline-block; border: 2px solid rgba(0, 0, 0, 0.1); font-family: 'Montserrat', Arial, sans-serif; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);">
                            Add My Dates{arrow_icon_button}
                        </a>
                    </div>
                    
                    <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">
                        Once everyone's in, you'll let us build your itinerary — all in minutes.
                    </p>
                    
                    <p style="font-size: 16px; color: #333; margin: 0 0 32px 0; font-family: 'Montserrat', Arial, sans-serif;">
                        Let's make sure this one <em>actually</em> leaves the group chat
                    </p>
                    
                    <p style="font-size: 16px; color: #333; margin: 32px 0 0 0; font-family: 'Montserrat', Arial, sans-serif;">
                        — Team Traverse
                    </p>

                    <hr style="border: none; border-top: 1px solid #eeeeee; margin: 40px 0 20px 0;">
                    
                    <p style="color: #999999; font-size: 12px; text-align: center; margin: 0; line-height: 1.5; font-family: 'Montserrat', Arial, sans-serif;">
                        This email was sent from an unmonitored address. Please do not reply to this email.<br>
                        If you have questions, please contact {organizer_name} directly or visit Traverse.
                    </p>
                </div>
            </body>
        </html>
        """

        return html

    def send_first_itinerary_email(
        self,
        recipient_email: str,
        recipient_first_name: str,
        destination: str,
        trip_name: str,
        trip_dates: str,
        itinerary_link: str,
    ) -> bool:
        """
        Send email when user creates their first itinerary.

        Args:
            recipient_email: Email address of the user
            recipient_first_name: First name of the user
            destination: Trip destination
            trip_name: Name of the trip
            trip_dates: Formatted trip dates
            itinerary_link: Link to view the itinerary

        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            feedback_form_url = "https://docs.google.com/forms/d/1C7dirJFuA76XrdDW0ZOcu0SQR5BqAcwHwZcOXqUzD3c/viewform?edit_requested=true"

            html_content = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
                </head>
                <body style="margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #ffffff;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 30px 20px;">
                        <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">Hi {recipient_first_name},</p>
                        
                        <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">
                            🎉 <strong style="font-weight: 600;">Congratulations on creating your first itinerary with Traverse!</strong>
                        </p>
                        
                        <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">
                            Your itinerary for <strong style="font-weight: 600;">{destination}</strong> is ready — packed with restaurants, activities, and hidden gems built around your preferences.
                        </p>
                        
                        <div style="background-color: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
                            <p style="margin: 10px 0; font-size: 16px;"><strong>📅 Trip:</strong> {trip_name}</p>
                            <p style="margin: 10px 0; font-size: 16px;"><strong>🗓️ Dates:</strong> {trip_dates}</p>
                        </div>

                        <div style="margin: 32px 0; text-align: center;">
                            <a href="{itinerary_link}" style="background-color: #a1f800; color: #000000; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 16px; display: inline-block; border: 2px solid rgba(0, 0, 0, 0.1); font-family: 'Montserrat', Arial, sans-serif; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);">
                                View your itinerary →
                            </a>
                        </div>

                        <p style="font-size: 16px; color: #333; margin: 32px 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">
                            Thanks for being an early user. Your feedback helps us improve.
                        </p>

                        <div style="margin: 24px 0; text-align: center;">
                            <a href="{feedback_form_url}" style="color: #a1f800; text-decoration: underline; font-size: 16px; font-weight: 600; font-family: 'Montserrat', Arial, sans-serif;">
                                Share your feedback →
                            </a>
                        </div>

                        <p style="font-size: 16px; color: #333; margin: 32px 0 0 0; font-family: 'Montserrat', Arial, sans-serif;">
                            Let's make sure this one <em>actually</em> leaves the group chat
                        </p>
                        
                        <p style="font-size: 16px; color: #333; margin: 32px 0 0 0; font-family: 'Montserrat', Arial, sans-serif;">
                            — Team Traverse
                        </p>

                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 40px 0 20px 0;">
                        
                        <p style="color: #999999; font-size: 12px; text-align: center; margin: 0; line-height: 1.5; font-family: 'Montserrat', Arial, sans-serif;">
                            This email was sent from an unmonitored address. Please do not reply to this email.<br>
                            If you have questions, please visit Traverse.
                        </p>
                    </div>
                </body>
            </html>
            """

            params = {
                "from": f"Traverse <{self.sender_email}>",
                "to": [recipient_email],
                "subject": f"Your {destination} itinerary is ready",
                "html": html_content,
            }

            response = resend.Emails.send(params)
            logger.info(f"Sent first itinerary email to {recipient_email}: {response}")
            return True

        except Exception as e:
            logger.error(
                f"Error sending first itinerary email to {recipient_email}: {e}"
            )
            return False

    def send_all_participants_responded_email(
        self,
        organizer_email: str,
        organizer_first_name: str,
        destination: str,
        trip_name: str,
        group_size: int,
        generate_link: str,
    ) -> bool:
        """
        Send email to organizer when all participants have responded.

        Args:
            organizer_email: Email address of the organizer
            organizer_first_name: First name of the organizer
            destination: Trip destination
            trip_name: Name of the trip
            group_size: Number of travelers (including organizer)
            generate_link: Link to generate the itinerary

        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            html_content = f"""
            <!DOCTYPE html>
            <html>
                <head>
                    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
                </head>
                <body style="margin: 0; padding: 0; font-family: 'Montserrat', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #ffffff;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 30px 20px;">
                        {self._get_logo_html()}
                        <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">Hi {organizer_first_name},</p>
                        
                        <p style="font-size: 16px; color: #333; margin: 0 0 20px 0; font-family: 'Montserrat', Arial, sans-serif;">
                            🎉 <strong style="font-weight: 600;">Everyone's in!</strong> Your group has submitted their dates and preferences for <strong style="font-weight: 600;">"{trip_name}"</strong> — now it's your turn to bring it all together.
                        </p>
                        
                        <div style="background-color: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
                            <p style="margin: 10px 0; font-size: 16px;"><strong>📍 Destination:</strong> {destination}</p>
                            <p style="margin: 10px 0; font-size: 16px;"><strong>👥 Group Size:</strong> {group_size} travelers</p>
                        </div>

                        <p style="font-size: 16px; color: #333; margin: 0 0 24px 0; font-family: 'Montserrat', Arial, sans-serif;">
                            We've analyzed everyone's inputs to suggest the best plan for your crew.
                        </p>

                        <div style="margin: 32px 0; text-align: center;">
                            <a href="{generate_link}" style="background-color: #a1f800; color: #000000; padding: 14px 32px; text-decoration: none; border-radius: 12px; font-weight: 700; font-size: 16px; display: inline-block; border: 2px solid rgba(0, 0, 0, 0.1); font-family: 'Montserrat', Arial, sans-serif; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);">
                                Generate Itinerary →
                            </a>
                        </div>

                        <p style="font-size: 16px; color: #333; margin: 32px 0 0 0; font-family: 'Montserrat', Arial, sans-serif;">
                            Let's make sure this one <em>actually</em> leaves the group chat
                        </p>
                        
                        <p style="font-size: 16px; color: #333; margin: 32px 0 0 0; font-family: 'Montserrat', Arial, sans-serif;">
                            — Team Traverse
                        </p>

                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 40px 0 20px 0;">
                        
                        <p style="color: #999999; font-size: 12px; text-align: center; margin: 0; line-height: 1.5; font-family: 'Montserrat', Arial, sans-serif;">
                            This email was sent from an unmonitored address. Please do not reply to this email.<br>
                            If you have questions, please visit Traverse.
                        </p>
                    </div>
                </body>
            </html>
            """

            params = {
                "from": f"Traverse <{self.sender_email}>",
                "to": [organizer_email],
                "subject": f"Your group's ready — time to finalize your {destination} trip",
                "html": html_content,
            }

            response = resend.Emails.send(params)
            logger.info(
                f"Sent all participants responded email to {organizer_email}: {response}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error sending all participants responded email to {organizer_email}: {e}"
            )
            return False


# Singleton instance
email_service = EmailService()


def send_trip_invite_email(
    to_email: str,
    invite_id: str,
    organizer_name: str,
    trip_name: str,
    destination: Optional[str] = None,
    date_range_start: Optional[str] = None,
    date_range_end: Optional[str] = None,
    custom_message: Optional[str] = None,
    recipient_first_name: Optional[str] = None,
) -> bool:
    """
    Convenience function to send trip invite email.

    Args:
        to_email: Recipient email address
        invite_id: Invite ID for the link
        organizer_name: Name of the organizer
        trip_name: Name of the trip
        destination: Optional destination
        date_range_start: Optional start date
        date_range_end: Optional end date
        custom_message: Optional custom message
        recipient_first_name: Optional first name of recipient (falls back to email-based generation)

    Returns:
        True if sent successfully, False otherwise
    """
    # Construct invite link
    # NOTE: FRONTEND_URL must be set to your public URL (e.g., ngrok URL) for emails to work
    # Emails require absolute URLs, so relative paths won't work here
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3456")
    invite_link = f"{frontend_url}/invite/{invite_id}"

    # Use recipient_first_name if provided, otherwise generate from email
    if recipient_first_name and recipient_first_name.strip():
        recipient_name = recipient_first_name.strip()
    else:
        # Fallback: extract recipient name from email
        recipient_name = to_email.split("@")[0].replace(".", " ").title()

    return email_service.send_trip_invite(
        recipient_email=to_email,
        recipient_name=recipient_name,
        organizer_name=organizer_name,
        trip_name=trip_name,
        destination=destination,
        date_range_start=date_range_start,
        date_range_end=date_range_end,
        custom_message=custom_message,
        invite_link=invite_link,
    )
