from django.conf import settings
from django.utils.translation import check_for_language
from django.utils.translation import get_supported_language_variant
from django.utils.translation.trans_real import get_languages
from django.utils.translation.trans_real import language_code_re
from django.utils.translation.trans_real import parse_accept_lang_header


def get_language(scope: dict) -> str:
    """
    scope:
        The connection scope from the (websocket/http) consumer.

    Get language according to this order:

    1) From cookie
    2) From Accept-Language HTTP header
    3) Default language from settings

    Note: This whole method should mimic the behaviour of Django's get_language_from_request
    for consistency. So yeah this code looks like this in Django.
    """

    lang_code = scope.get("cookies", {}).get(settings.LANGUAGE_COOKIE_NAME)

    if (
        lang_code is not None
        and lang_code in get_languages()
        and check_for_language(lang_code)
    ):
        return lang_code
    try:
        return get_supported_language_variant(lang_code)
    except LookupError:
        pass
    accept = []
    for (k, v) in scope.get("headers", {}):
        if k == b"accept-language":
            accept.append(v.decode())
        elif k == "accept-language":
            # Mostly for testing or in case this changes
            accept.append(v)
    if accept:
        accept_str = ",".join(accept)
        for accept_lang, unused in parse_accept_lang_header(accept_str):
            if accept_lang == "*":
                break
            if not language_code_re.search(accept_lang):
                continue
            try:
                return get_supported_language_variant(accept_lang)
            except LookupError:
                continue
    try:
        return get_supported_language_variant(settings.LANGUAGE_CODE)
    except LookupError:
        return settings.LANGUAGE_CODE
