# DSG Spacetime — Public Source Candidate

Status: **PREPARED — NOT YET PUBLISHED**

DSG Spacetime is a customer-hosted governed runtime for composing and executing node-to-node AI workflows with plan binding, fail-closed authorization, offline entitlement verification, and tamper-evident evidence records.

## Publication boundary

This candidate contains the reviewed runtime implementation and non-commerce tests from the audited production snapshot `e8b27cad7136ac65bd6916f27cc3a6e65786ab36`.

It intentionally does **not** contain seller signing material, seller trust-root injection tooling, Stripe/Resend fulfillment, customer or transaction records, private commercial packaging, private release workflows, commercial runtime artifacts, or internal operator/continuity records.

## Source versus commercial binary

The source tree is inspectable and runnable as Python source. It supports caller-selected trust roots in source/library paths used by tests and development. Do not treat this source distribution as technically equivalent to the seller-trust-root-locked compiled commercial binary.

Commercial builds may inject a seller trust root and apply separate private build, signing, packaging, and anti-bypass verification outside this repository.

## Candidate usage

Python 3.11+ is required for authorized evaluation and development under separately granted rights.

```bash
python -m pip install -e '.[dev]'
pytest -q
```

CLI entry point:

```bash
dsg-spacetime --help
```

## License status

Final source-visible terms have been selected: **Proprietary / all rights reserved** under the `DSG SPACETIME PROPRIETARY SOURCE-VISIBLE LICENSE` included as `LICENSE`.

Public visibility is provided for inspection and evaluation only under those terms. It is **not** an open-source license and does not grant a general right to use, modify, redistribute, sublicense, commercialize, or create derivative works from the source.

Publication remains blocked until the source-public policy boundary is explicitly superseded, the candidate is transferred into a new clean-history public repository, public CI succeeds on that repository, and post-publication repository/provider state is verified.
