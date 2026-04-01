"""Math module for Berb.

Computational verification of mathematical content based on
HorizonMath principle: "Discovery is hard, verification is easy."

# Author: Georgios-Chrysovalantis Chatzivantsidis
"""

from .verification import (
    VerifiableMathContent,
    VerifiedTheorem,
    VerificationReport,
    verify_theorem,
    verify_equation,
)

__all__ = [
    "VerifiableMathContent",
    "VerifiedTheorem",
    "VerificationReport",
    "verify_theorem",
    "verify_equation",
]
