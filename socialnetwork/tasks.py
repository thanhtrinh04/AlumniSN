import os

from celery import shared_task
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from django.db import DatabaseError
from django.apps import apps
import logging
