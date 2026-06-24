import sys
from unittest.mock import MagicMock
import google.auth
import google.auth.credentials

# Mock google.auth.default to return dummy credentials and project ID
dummy_credentials = MagicMock(spec=google.auth.credentials.Credentials)
dummy_credentials.token = "dummy-token"
dummy_credentials.valid = True
google.auth.default = lambda *args, **kwargs: (dummy_credentials, "my-project")
