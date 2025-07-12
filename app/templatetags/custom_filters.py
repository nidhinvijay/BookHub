from django import template

register = template.Library()

@register.filter(name='replace')
def replace(value, arg):
    """
    Replaces all occurrences of a substring with another substring.
    Usage: {{ value|replace:"old,new" }}
    """
    if not isinstance(value, str):
        return value
    try:
        old, new = arg.split(',')
        return value.replace(old, new)
    except ValueError:
        return value # Return original value if arg is not in 'old,new' format
    
register = template.Library()

@register.filter
def replace_http_with_https(value):
    """
    Replaces 'http://' with 'https://' in a URL string.
    Useful for ensuring image URLs are secure.
    """
    if isinstance(value, str) and value.startswith('http://'):
        return value.replace('http://', 'https://', 1)
    return value
