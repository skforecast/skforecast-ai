# Unit test ModelPolicy.model_of

from skforecast_ai.mcp._foundation import ModelPolicy


def test_model_policy_model_of_foundation_plans_only():
    """
    Test that only `ForecasterFoundation` has a model, the default one when
    no estimator is given.
    """
    policy = ModelPolicy()

    assert policy.model_of("ForecasterRecursive", "Ridge") is None
    assert policy.model_of(None, None) is None
    assert policy.model_of("ForecasterFoundation", None) == "autogluon/chronos-2-small"
    assert policy.model_of("ForecasterFoundation", "Synthefy/Nori") == "Synthefy/Nori"
