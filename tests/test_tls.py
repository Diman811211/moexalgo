import hashlib
import ssl
from importlib import resources
from unittest.mock import patch

import httpx
import pytest

from moexalgo._tls import create_moex_ssl_context
from moexalgo.session import BaseClient

RUSSIAN_ROOT_FINGERPRINT = "D26D2D0231B7C39F92CC738512BA54103519E4405D68B5BD703E9788CA8ECF31"


def _certificate_fingerprints(context: ssl.SSLContext) -> set[str]:
    return {hashlib.sha256(certificate).hexdigest().upper() for certificate in context.get_ca_certs(binary_form=True)}


def test_packaged_russian_root_has_expected_fingerprint() -> None:
    certificate = resources.files("moexalgo").joinpath("certs/russian_trusted_root_ca.crt").read_text(encoding="ascii")

    certificate_der = ssl.PEM_cert_to_DER_cert(certificate)
    fingerprint = hashlib.sha256(certificate_der).hexdigest().upper()

    assert fingerprint == RUSSIAN_ROOT_FINGERPRINT


def test_moex_context_combines_httpx_roots_with_russian_root() -> None:
    httpx_context = httpx.create_ssl_context(verify=True, trust_env=False)

    moex_context = create_moex_ssl_context(trust_env=False)

    httpx_fingerprints = _certificate_fingerprints(httpx_context)
    moex_fingerprints = _certificate_fingerprints(moex_context)
    assert httpx_fingerprints <= moex_fingerprints
    assert RUSSIAN_ROOT_FINGERPRINT in moex_fingerprints
    assert moex_context.verify_mode == ssl.CERT_REQUIRED
    assert moex_context.check_hostname is True


def test_moex_context_forwards_trust_env_to_httpx() -> None:
    httpx_context = ssl.create_default_context()

    with patch(
        "moexalgo._tls.httpx.create_ssl_context", autospec=True, return_value=httpx_context
    ) as create_httpx_context:
        result = create_moex_ssl_context(trust_env=False)

    assert result is httpx_context
    create_httpx_context.assert_called_once_with(verify=True, trust_env=False)


def test_base_client_uses_combined_context_by_default() -> None:
    moex_context = ssl.create_default_context()

    with (
        patch("moexalgo.session.create_moex_ssl_context", autospec=True, return_value=moex_context) as create_context,
        patch("moexalgo.session.httpx.Client", autospec=True) as httpx_client,
    ):
        BaseClient(trust_env=False)

    create_context.assert_called_once_with(trust_env=False)
    assert httpx_client.call_args.kwargs["verify"] is moex_context
    assert httpx_client.call_args.kwargs["trust_env"] is False


@pytest.mark.parametrize(
    "verify",
    [
        pytest.param(False, id="disabled"),
        pytest.param(True, id="httpx-default"),
        pytest.param(ssl.create_default_context(), id="custom-context"),
    ],
)
def test_base_client_preserves_explicit_verify(verify: bool | ssl.SSLContext) -> None:
    with (
        patch("moexalgo.session.create_moex_ssl_context", autospec=True) as create_context,
        patch("moexalgo.session.httpx.Client", autospec=True) as httpx_client,
    ):
        BaseClient(verify=verify)

    create_context.assert_not_called()
    assert httpx_client.call_args.kwargs["verify"] is verify
