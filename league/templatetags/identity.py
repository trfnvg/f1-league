from django import template
from league.identity import display_name

register = template.Library()
register.filter("player_name", display_name)
