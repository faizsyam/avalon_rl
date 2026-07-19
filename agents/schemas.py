"""Pydantic schemas for all LLM output validation in the Avalon agent system.

Length limits are intentionally generous — Llama occasionally writes 800+ char
strategic statements; an under-sized cap here causes silent retries and burn.
Hard cap at 4000 chars catches runaway output without rejecting substantive replies.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class DiscussionOutput(BaseModel):
    statement: str = Field(..., min_length=1, max_length=4000, description="Public statement made during discussion")
    private_note: str = Field(default="", max_length=4000, description="Private reasoning about the statement")


class RejectionReactionOutput(BaseModel):
    statement: str = Field(..., min_length=1, max_length=4000, description="Brief public reaction to rejected proposal")
    private_note: str = Field(default="", max_length=4000, description="Private interpretation of the vote result")


class ProposalOutput(BaseModel):
    proposed_team: List[str] = Field(..., min_length=2, max_length=3, description="List of player names for the mission team")
    speech: str = Field(..., min_length=1, max_length=4000, description="Public announcement naming the same players")
    private_note: str = Field(default="", max_length=4000, description="Leader's private reasoning for the proposal")


class VoteOutput(BaseModel):
    vote: str = Field(..., pattern="^(APPROVE|REJECT)$", description="APPROVE or REJECT")
    speech: str = Field(..., min_length=1, max_length=4000, description="Public stated reason for the vote")
    private_note: str = Field(default="", max_length=4000, description="Private reasoning behind the vote")


class MissionOutput(BaseModel):
    card: str = Field(..., pattern="^(SUCCESS|FAIL)$", description="SUCCESS or FAIL")
    internal_note: str = Field(default="", max_length=4000, description="Private reasoning for the card play")


class AssassinOutput(BaseModel):
    guess_name: str = Field(..., min_length=1, max_length=4000, description="Name of the player guessed as Merlin")
    reasoning: str = Field(..., min_length=1, max_length=4000, description="Full analysis for the guess")


class AnalysisOutput(BaseModel):
    certain_facts: str = Field(default="", max_length=4000, description="Mathematical certainties from quest math")
    suspicion_model: str = Field(default="", max_length=4000, description="Read on each player with specific evidence")
    contradiction: str = Field(default="", max_length=4000, description="Any player who contradicted a prior statement")
    priority: str = Field(default="", max_length=4000, description="Single most important objective this round")


class ReflectionDeltaOutput(BaseModel):
    add_tentative: List[Dict[str, Any]] = Field(default_factory=list)
    confirm_active: List[Dict[str, Any]] = Field(default_factory=list)
    flag_deprecated: List[Dict[str, Any]] = Field(default_factory=list)


class CoordinatorOutput(BaseModel):
    add_tentative: List[Dict[str, Any]] = Field(default_factory=list)
    confirm_active: List[Dict[str, Any]] = Field(default_factory=list)
    flag_deprecated: List[Dict[str, Any]] = Field(default_factory=list)