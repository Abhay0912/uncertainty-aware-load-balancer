import pytest

import lbsim
from lbsim.policies import Policy


def test_package_imports():
    assert lbsim.__version__


def test_policy_is_abstract():
    with pytest.raises(TypeError):
        Policy()
