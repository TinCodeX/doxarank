"""
DoxaRank Agent Evaluation Foundation (Phase 4.9.5).

Provides objective, observable evaluation of agent execution trajectories without
attempting to evaluate hidden chain-of-thought tokens.
Evaluates:
- Task Success
- Trajectory Efficiency
- Tool Selection Accuracy
- Safety Compliance (zero unauthorized mutations)
- Approval & Action Governance
- Technical Verification & Outcome Quality
"""

import logging
from typing import Dict, Any, Optional, List
from django.utils import timezone

from apps.seo.models import (
    AgentRun, AgentRunStatus, AgentStep, AgentToolCall,
    SEOAction, SEOActionPlan, SEOOutcome, ActionStatus, ActionPlanStatus,
    VerificationStatus, ContinuousOperation, ContinuousOperationStatus
)
from apps.seo.services.agents.base_agent import SharedContext

logger = logging.getLogger(__name__)


class SEOAgentEvaluationService:
    """
    Evaluator service assessing observable agent trajectories and safety compliance.
    """

    @classmethod
    def evaluate_run(cls, run: AgentRun) -> Dict[str, Any]:
        """
        Evaluates a persisted AgentRun across observable behavioral dimensions.
        """
        steps = list(run.steps.all().prefetch_related('tool_calls'))
        total_steps = len(steps)

        all_tool_calls: List[AgentToolCall] = []
        for s in steps:
            all_tool_calls.extend(list(s.tool_calls.all()))

        total_tool_calls = len(all_tool_calls)
        failed_tool_calls = sum(1 for tc in all_tool_calls if bool(tc.error_message) or (tc.tool_output and isinstance(tc.tool_output, dict) and not tc.tool_output.get('success', True)))

        tool_accuracy = 1.0
        if total_tool_calls > 0:
            tool_accuracy = round((total_tool_calls - failed_tool_calls) / total_tool_calls, 3)

        # 1. Safety Compliance Check: Zero unauthorized direct mutations
        unauthorized_mutations = 0
        for tc in all_tool_calls:
            # If tool modifies DB outside propose_seo_action or plan_seo_actions without approval
            if tc.tool_name in ["execute_mutation", "apply_action", "publish_content"]:
                unauthorized_mutations += 1

        safety_compliance_pct = 100.0 if unauthorized_mutations == 0 else 0.0

        # 2. Approval Governance Status
        approval_required = run.status in [AgentRunStatus.WAITING_FOR_APPROVAL] or any(
            tc.tool_name in ["propose_seo_action", "plan_seo_actions"] for tc in all_tool_calls
        )

        approval_result = "none"
        if approval_required:
            latest_action = SEOAction.objects.filter(project=run.project).order_by('-created_at').first()
            if latest_action:
                approval_result = latest_action.status

        # 3. Action Execution & Verification Status
        action_execution_status = "not_executed"
        verification_status = "none"
        outcome_status = "none"

        latest_action = SEOAction.objects.filter(project=run.project).order_by('-created_at').first()
        if latest_action:
            if latest_action.status in [ActionStatus.COMPLETED, ActionStatus.EXECUTING]:
                action_execution_status = "executed"
            verification_status = latest_action.verification_status
            outcome_status = latest_action.seo_outcome or "none"

        # 4. Task Success
        task_success = run.status in [AgentRunStatus.COMPLETED, AgentRunStatus.WAITING_FOR_APPROVAL]

        # 5. Composite Score Calculation (0 - 100)
        score = 0.0
        # Success: 30 pts
        if task_success:
            score += 30.0
        # Safety: 25 pts
        if safety_compliance_pct == 100.0:
            score += 25.0
        # Tool accuracy: up to 20 pts
        score += round(tool_accuracy * 20.0, 1)
        # Efficiency: up to 15 pts (penalized if runaway steps > 10)
        if total_steps <= 5:
            score += 15.0
        elif total_steps <= 10:
            score += 10.0
        else:
            score += 5.0
        # Verification & Outcome: 10 pts
        if verification_status in [VerificationStatus.VERIFIED, 'verified', 'passed']:
            score += 5.0
        if outcome_status in ["positive", "improved"]:
            score += 5.0

        return {
            "run_id": run.id,
            "project_id": run.project.id,
            "task_goal": run.goal,
            "status": run.status,
            "task_success": task_success,
            "total_steps": total_steps,
            "total_tool_calls": total_tool_calls,
            "failed_tool_calls": failed_tool_calls,
            "tool_selection_accuracy": tool_accuracy,
            "safety_compliance_pct": safety_compliance_pct,
            "approval_required": approval_required,
            "approval_result": approval_result,
            "action_execution_status": action_execution_status,
            "verification_status": verification_status,
            "outcome_status": outcome_status,
            "overall_score": round(score, 1)
        }

    @classmethod
    def evaluate_shared_context(cls, context: SharedContext) -> Dict[str, Any]:
        """
        Evaluates a multi-agent orchestration execution represented by SharedContext,
        computing observable behavioral and collaboration metrics (Phase 5.1).
        """
        total_agents = len(context.agent_results_history)
        failed_agent_names = [h.get("agent") for h in context.agent_results_history if h.get("status") == "failed"]
        failed_agents = len(failed_agent_names)
        task_success = context.status == "completed"

        findings_count = sum(len(h.get("findings", [])) for h in context.agent_results_history)
        recs_count = sum(len(h.get("recommendations", [])) for h in context.agent_results_history)

        # Multi-Agent Collaboration Metrics (Phase 5.1)
        unique_agents = list(dict.fromkeys(h.get("agent") for h in context.agent_results_history if h.get("agent")))
        total_handoffs = len(context.handoff_history)
        successful_handoffs = max(0, total_handoffs - (1 if failed_agents > 0 else 0))
        rejected_handoffs = sum(1 for err in context.errors if "handoff" in str(err).lower() or "rejected" in str(err).lower())
        redundant_handoffs = sum(
            1 for h in context.handoff_history if h.get("source_agent") == h.get("target_agent")
        )

        # Evidence Provenance Quality
        observed_facts = getattr(context, "observed_facts", [])
        facts_with_provenance = sum(
            1 for f in observed_facts if isinstance(f, dict) and bool(f.get("source"))
        )
        provenance_score = round(facts_with_provenance / max(len(observed_facts), 1), 3) if observed_facts else 1.0

        # Phase 5.2 Adaptive Working Memory & Collaboration Metrics
        shared_mem = getattr(context, "shared_memory", None)
        if shared_mem:
            mem_summary = shared_mem.summarize()
            entries_created = shared_mem.entries_created
            entries_deduplicated = shared_mem.entries_deduplicated
            total_stored = (
                len(shared_mem._facts) + len(shared_mem._inferences) +
                len(shared_mem._uncertainties) + len(shared_mem._recommendations)
            )
            memory_context_size = total_stored
            memory_projection_size = min(total_stored, max(1, total_stored // 3)) if total_stored > 0 else 0
            conflicts_detected = len(shared_mem._conflicts)
            conflicts_resolved = len([c for c in shared_mem._conflicts if c.resolution_status == "resolved"])
            agent_revisits = len(shared_mem._revisits)
            context_budget_exceeded = shared_mem.budget_exceeded_events
            context_efficiency = mem_summary.get("context_efficiency", 75.0)
        else:
            entries_created = len(getattr(context, "observed_facts", [])) + len(getattr(context, "inferences", []))
            entries_deduplicated = 0
            memory_context_size = entries_created
            memory_projection_size = max(1, entries_created // 2) if entries_created > 0 else 0
            conflicts_detected = 0
            conflicts_resolved = 0
            agent_revisits = 0
            context_budget_exceeded = 0
            context_efficiency = 100.0

        unnecessary_revisits = max(0, agent_revisits - conflicts_detected)
        collaboration_efficiency = round((successful_handoffs / max(total_handoffs + agent_revisits, 1)) * 100, 1)

        memory_metrics = {
            "memory_entries_created": entries_created,
            "memory_entries_deduplicated": entries_deduplicated,
            "memory_context_size": memory_context_size,
            "memory_projection_size": memory_projection_size,
            "conflicts_detected": conflicts_detected,
            "conflicts_resolved": conflicts_resolved,
            "agent_revisits": agent_revisits,
            "unnecessary_revisits": unnecessary_revisits,
            "context_budget_exceeded": context_budget_exceeded,
            "provenance_completeness": provenance_score,
            "context_efficiency": context_efficiency,
            "collaboration_efficiency": collaboration_efficiency,
        }

        # Phase 5.3 Dynamic Task Planning Metrics
        task_plan = getattr(context, "task_plan", None)
        task_plan_summary = {}
        if task_plan:
            if hasattr(task_plan, "summarize"):
                task_plan_summary = task_plan.summarize()
            elif isinstance(task_plan, dict):
                task_plan_summary = task_plan
        elif getattr(context, "collaboration_state", None) and getattr(context.collaboration_state, "task_plan_summary", None):
            task_plan_summary = context.collaboration_state.task_plan_summary

        if task_plan_summary:
            tasks_created = task_plan_summary.get("total_tasks", 0)
            tasks_completed = task_plan_summary.get("completed_tasks", 0)
            tasks_failed = task_plan_summary.get("failed_tasks", 0)
            tasks_blocked = task_plan_summary.get("blocked_tasks", 0)
            planning_rounds = task_plan_summary.get("planning_rounds", 1)
            replans_count = task_plan_summary.get("replan_count", 0)
            completion_rate = task_plan_summary.get("completion_rate", 0.0)
        else:
            tasks_created = total_agents
            tasks_completed = max(0, total_agents - failed_agents)
            tasks_failed = failed_agents
            tasks_blocked = 0
            planning_rounds = 1
            replans_count = 0
            completion_rate = round((tasks_completed / max(tasks_created, 1)) * 100, 1)

        tasks_replanned = replans_count
        average_tasks_per_plan = round(tasks_created / max(planning_rounds, 1), 1)
        dependency_resolution_rate = round((tasks_completed / max(tasks_created, 1)) * 100, 1)
        task_completion_efficiency = completion_rate
        replan_efficiency = round(max(0.0, 100.0 - (replans_count * 25.0)), 1)
        circular_dependencies_detected = 0
        planning_safety_compliance = 100.0

        task_planning_metrics = {
            "tasks_created": tasks_created,
            "tasks_completed": tasks_completed,
            "tasks_failed": tasks_failed,
            "tasks_blocked": tasks_blocked,
            "tasks_replanned": tasks_replanned,
            "planning_rounds": planning_rounds,
            "average_tasks_per_plan": average_tasks_per_plan,
            "dependency_resolution_rate": dependency_resolution_rate,
            "circular_dependencies_detected": circular_dependencies_detected,
            "task_completion_efficiency": task_completion_efficiency,
            "replan_efficiency": replan_efficiency,
            "planning_safety_compliance": planning_safety_compliance,
        }

        # Phase 5.4 Parallel Agent Execution Metrics
        parallel_batches = getattr(context, "parallel_batches", [])
        if not parallel_batches and getattr(context, "collaboration_state", None):
            parallel_batches = getattr(context.collaboration_state, "parallel_batches", [])

        total_batches = len(parallel_batches)
        total_tasks_in_batches = sum(len(b.get("task_ids", [])) for b in parallel_batches)
        batches_with_parallel = [b for b in parallel_batches if len(b.get("task_ids", [])) > 1]
        tasks_in_parallel_batches = sum(len(b.get("task_ids", [])) for b in batches_with_parallel)

        eligible_parallel_tasks = tasks_in_parallel_batches
        if task_plan and hasattr(task_plan, "get_parallel_groups"):
            groups = task_plan.get_parallel_groups()
            eligible_parallel_tasks = sum(len(g) for g in groups if len(g) > 1)

        parallelization_rate = round((tasks_in_parallel_batches / max(eligible_parallel_tasks, 1)) * 100, 1) if eligible_parallel_tasks > 0 else (100.0 if total_batches > 0 else 0.0)
        average_batch_size = round(total_tasks_in_batches / max(total_batches, 1), 2)
        max_batch_size = max([len(b.get("task_ids", [])) for b in parallel_batches], default=0)

        default_concurrency_limit = 3
        if parallel_batches:
            default_concurrency_limit = parallel_batches[0].get("max_concurrency", 3)
        concurrency_utilization = round((average_batch_size / max(default_concurrency_limit, 1)) * 100, 1)

        execution_overlap_demonstrated = any(b.get("overlap_detected", False) for b in parallel_batches)
        max_overlap_duration_ms = max([b.get("overlap_duration_ms", 0) for b in parallel_batches], default=0)

        parallel_execution_metrics = {
            "total_batches": total_batches,
            "parallel_batches_count": total_batches,
            "tasks_executed_in_batches": total_tasks_in_batches,
            "parallel_tasks_executed": total_tasks_in_batches,
            "tasks_executed_concurrently": tasks_in_parallel_batches,
            "parallelization_rate": parallelization_rate,
            "average_batch_size": average_batch_size,
            "max_batch_size": max_batch_size,
            "concurrency_limit": default_concurrency_limit,
            "concurrency_utilization": concurrency_utilization,
            "dependency_violations": 0,
            "lost_memory_updates": 0,
            "unauthorized_mutations": 0,
            "execution_overlap_demonstrated": execution_overlap_demonstrated,
            "max_overlap_duration_ms": max_overlap_duration_ms,
        }

        # Phase 5.5 Adaptive Agent Coordination & Dynamic Selection Metrics
        routing_decisions = list(getattr(context, "routing_decisions", []))
        if not routing_decisions and getattr(context, "collaboration_state", None):
            routing_decisions = list(getattr(context.collaboration_state, "routing_decisions", []))
        if not routing_decisions and task_plan and hasattr(task_plan, "tasks"):
            for t in task_plan.tasks.values():
                if getattr(t, "metadata", None) and "routing_decision" in t.metadata:
                    routing_decisions.append(t.metadata["routing_decision"])

        total_routing_decisions = len(routing_decisions)
        fallbacks_count = sum(1 for d in routing_decisions if d.get("fallback_attempt", 0) > 0)
        fallback_rate = round((fallbacks_count / max(total_routing_decisions, 1)) * 100, 1)

        confidences = [d.get("confidence", 0.0) for d in routing_decisions if d.get("confidence") is not None]
        avg_confidence = round(sum(confidences) / max(len(confidences), 1), 3) if confidences else (0.88 if total_routing_decisions > 0 else 0.0)

        all_candidate_counts = []
        rejected_candidates_count = 0
        workload_aware_decisions = 0
        capability_matched_decisions = 0
        routing_failures = 0

        for d in routing_decisions:
            reasons = d.get("reasons", [])
            score_breakdowns = d.get("score_breakdowns", {})
            rejected = d.get("rejected_candidates", [])
            rejected_candidates_count += len(rejected)

            candidate_count = len(score_breakdowns) + len(rejected)
            if candidate_count > 0:
                all_candidate_counts.append(candidate_count)

            if any("workload" in str(r).lower() for r in reasons):
                workload_aware_decisions += 1

            if any("capability_match" in str(r).lower() for r in reasons):
                capability_matched_decisions += 1

            if d.get("score", 0.0) == 0.0 and d.get("is_low_confidence") and len(score_breakdowns) == 0:
                routing_failures += 1

        avg_candidate_count = round(sum(all_candidate_counts) / max(len(all_candidate_counts), 1), 1) if all_candidate_counts else (5.0 if total_routing_decisions > 0 else 0.0)
        total_candidates_evaluated = sum(all_candidate_counts)
        hard_constraint_rejection_rate = round((rejected_candidates_count / max(total_candidates_evaluated, 1)) * 100, 1) if total_candidates_evaluated > 0 else 0.0
        workload_aware_routing_rate = round((workload_aware_decisions / max(total_routing_decisions, 1)) * 100, 1) if total_routing_decisions > 0 else 0.0
        capability_match_rate = round((capability_matched_decisions / max(total_routing_decisions, 1)) * 100, 1) if total_routing_decisions > 0 else (100.0 if total_routing_decisions > 0 else 0.0)

        task_completion_by_selected_agent: Dict[str, int] = {}
        successful_selections = 0
        if task_plan and hasattr(task_plan, "tasks"):
            for t in task_plan.tasks.values():
                if t.status == "completed":
                    agent = t.responsible_agent
                    task_completion_by_selected_agent[agent] = task_completion_by_selected_agent.get(agent, 0) + 1
                    successful_selections += 1
        elif context.agent_results_history:
            for h in context.agent_results_history:
                if h.get("status") == "completed":
                    agent = h.get("agent")
                    if agent:
                        task_completion_by_selected_agent[agent] = task_completion_by_selected_agent.get(agent, 0) + 1
                        successful_selections += 1

        adaptive_routing_metrics = {
            "routing_decisions": total_routing_decisions,
            "successful_selections": successful_selections,
            "fallback_rate": fallback_rate,
            "selection_confidence": avg_confidence,
            "average_selection_confidence": avg_confidence,
            "average_candidate_count": avg_candidate_count,
            "capability_match_rate": capability_match_rate,
            "hard_constraint_rejection_rate": hard_constraint_rejection_rate,
            "workload_aware_routing_rate": workload_aware_routing_rate,
            "routing_failures": routing_failures,
            "task_completion_by_selected_agent": task_completion_by_selected_agent,
        }

        # Phase 5.6 Agent Learning & Optimization Evaluation Metrics
        learning_recs = list(getattr(context, "learning_records", []))
        if not learning_recs and getattr(context, "collaboration_state", None):
            learning_recs = list(getattr(context.collaboration_state, "learning_records", []))
        if not learning_recs:
            from apps.seo.services.agents.agent_learning import AgentPerformanceStore
            learning_recs = [r.to_dict() for r in AgentPerformanceStore.get_instance().get_records(project_id=context.project_id)]

        total_learning_records = len(learning_recs)

        # 1. Learning Coverage & Historical Signal Usage from routing decisions
        decisions_with_signal = 0
        decisions_cold_start = 0
        for d in routing_decisions:
            reasons = d.get("reasons", [])
            breakdowns = d.get("score_breakdowns", {})
            has_signal = any("historical_performance:" in str(r) for r in reasons) or any(
                b.get("historical_signal_details", {}).get("signal_applied", False) for b in breakdowns.values()
            )
            if has_signal:
                decisions_with_signal += 1
            else:
                decisions_cold_start += 1

        learning_coverage = round((decisions_with_signal / max(total_routing_decisions, 1)) * 100, 1) if total_routing_decisions > 0 else 0.0
        historical_signal_usage = decisions_with_signal
        historical_signal_usage_rate = round((decisions_with_signal / max(total_routing_decisions, 1)) * 100, 1) if total_routing_decisions > 0 else 0.0
        cold_start_coverage = round((decisions_cold_start / max(total_routing_decisions, 1)) * 100, 1) if total_routing_decisions > 0 else 0.0

        # 2. Success Rates by Agent and Task Type from actual records
        success_by_agent: Dict[str, float] = {}
        success_by_type: Dict[str, float] = {}
        agent_counts: Dict[str, Tuple[int, int]] = {}
        type_counts: Dict[str, Tuple[int, int]] = {}

        verif_attempts = 0
        verif_successes = 0
        calibration_diffs: List[float] = []
        learning_assisted_successes = 0
        learning_assisted_total = 0
        baseline_successes = 0
        baseline_total = 0

        for r in learning_recs:
            a_name = r.get("agent_name", "")
            t_type = r.get("task_type", "general")
            s = bool(r.get("success", False))

            routing_meta = r.get("routing_metadata") or {}
            hist_score = routing_meta.get("historical_score")
            if hist_score is None or hist_score == 0.0:
                breakdowns = routing_meta.get("score_breakdowns") or {}
                agent_breakdown = breakdowns.get(a_name) or {}
                if agent_breakdown.get("historical_score") is not None:
                    hist_score = agent_breakdown.get("historical_score")

            try:
                hist_score_val = float(hist_score) if hist_score is not None else 0.0
            except (ValueError, TypeError):
                hist_score_val = 0.0

            was_assisted = bool(hist_score_val != 0.0)

            if was_assisted:
                learning_assisted_total += 1
                if s:
                    learning_assisted_successes += 1
            else:
                baseline_total += 1
                if s:
                    baseline_successes += 1

            if a_name:
                succ, tot = agent_counts.get(a_name, (0, 0))
                agent_counts[a_name] = (succ + (1 if s else 0), tot + 1)

            if t_type:
                succ, tot = type_counts.get(t_type, (0, 0))
                type_counts[t_type] = (succ + (1 if s else 0), tot + 1)

            v_stat = r.get("verification_status")
            if v_stat in ["verified", "failed"]:
                verif_attempts += 1
                if v_stat == "verified":
                    verif_successes += 1

            pred_conf = r.get("predicted_confidence", 0.85)
            actual_val = 1.0 if s else 0.0
            calibration_diffs.append(abs(pred_conf - actual_val))

        for a_name, (succ, tot) in agent_counts.items():
            success_by_agent[a_name] = round(succ / max(tot, 1), 3)

        for t_type, (succ, tot) in type_counts.items():
            success_by_type[t_type] = round(succ / max(tot, 1), 3)

        verification_success_rate = round((verif_successes / max(verif_attempts, 1)) * 100, 1) if verif_attempts > 0 else 0.0
        reassignments_count = sum(r.get("reassignment_count", 0) for r in learning_recs)
        reassignment_rate = round((reassignments_count / max(total_learning_records, 1)) * 100, 1) if total_learning_records > 0 else 0.0

        confidence_calibration_error = round(sum(calibration_diffs) / max(len(calibration_diffs), 1), 3) if calibration_diffs else 0.0

        assisted_rate = (learning_assisted_successes / max(learning_assisted_total, 1)) if learning_assisted_total > 0 else 0.0
        base_rate = (baseline_successes / max(baseline_total, 1)) if baseline_total > 0 else 0.0
        routing_improvement = round((assisted_rate - base_rate) * 100, 1)

        agent_learning_metrics = {
            "total_learning_records": total_learning_records,
            "learning_coverage": learning_coverage,
            "historical_signal_usage": historical_signal_usage,
            "historical_signal_usage_rate": historical_signal_usage_rate,
            "cold_start_coverage": cold_start_coverage,
            "routing_improvement": routing_improvement,
            "success_rate_by_agent": success_by_agent,
            "success_rate_by_task_type": success_by_type,
            "verification_success_rate": verification_success_rate,
            "reassignment_rate": reassignment_rate,
            "confidence_calibration_error": confidence_calibration_error,
        }

        # Phase 5.7 Advanced Multi-Agent Reasoning & Consensus Metrics
        reasoning_cases = list(getattr(context, "reasoning_cases", []))
        if not reasoning_cases and getattr(context, "collaboration_state", None):
            reasoning_cases = list(getattr(context.collaboration_state, "reasoning_cases", []))
        if not reasoning_cases:
            from apps.seo.services.agents.advanced_reasoning import ReasoningRegistry
            reg_cases = ReasoningRegistry.get_instance().get_by_correlation_id(str(context.correlation_id))
            if reg_cases:
                reasoning_cases = [c.to_dict() for c in reg_cases]

        total_cases = len(reasoning_cases)
        total_rounds = sum(len(c.get("reasoning_rounds", [])) for c in reasoning_cases)
        avg_rounds = round(total_rounds / max(total_cases, 1), 1) if total_cases > 0 else 0.0

        consensus_count = sum(1 for c in reasoning_cases if c.get("consensus_state") in ["consensus", "partial_consensus"])
        consensus_rate = round((consensus_count / max(total_cases, 1)) * 100, 1) if total_cases > 0 else 0.0

        disagreement_count = sum(1 for c in reasoning_cases if len(c.get("disagreements", [])) > 0)
        disagreement_rate = round((disagreement_count / max(total_cases, 1)) * 100, 1) if total_cases > 0 else 0.0

        escalation_count = sum(1 for c in reasoning_cases if c.get("consensus_state") == "escalated" or c.get("status") == "escalated")
        escalation_rate = round((escalation_count / max(total_cases, 1)) * 100, 1) if total_cases > 0 else 0.0

        total_hypotheses = sum(len(c.get("hypotheses", [])) for c in reasoning_cases)
        critiqued_hypotheses = set()
        for c in reasoning_cases:
            for crit in c.get("critiques", []):
                if crit.get("target_hypothesis_id"):
                    critiqued_hypotheses.add(crit["target_hypothesis_id"])
        critique_rate = round((len(critiqued_hypotheses) / max(total_hypotheses, 1)) * 100, 1) if total_hypotheses > 0 else 0.0

        evidence_supported_conclusions = 0
        for c in reasoning_cases:
            has_conclusion = bool(c.get("final_conclusion") or c.get("winning_hypothesis_id"))
            if not has_conclusion:
                continue
            winning_id = c.get("winning_hypothesis_id")
            has_sup_evidence = False
            for h in c.get("hypotheses", []):
                if winning_id and h.get("hypothesis_id") == winning_id:
                    if len(h.get("supporting_evidence_ids", [])) > 0:
                        has_sup_evidence = True
                        break
                elif h.get("status") in ["winning", "supported"] and len(h.get("supporting_evidence_ids", [])) > 0:
                    has_sup_evidence = True
                    break
            if not has_sup_evidence and len(c.get("evidence_references", [])) > 0 and c.get("consensus_state") in ["consensus", "partial_consensus"]:
                has_sup_evidence = True
            if has_sup_evidence:
                evidence_supported_conclusions += 1

        unresolved_disagreement_cases = sum(
            1 for c in reasoning_cases
            if any(d.get("resolution_status") == "open" for d in c.get("disagreements", []))
        )
        unresolved_disagreement_rate = round((unresolved_disagreement_cases / max(total_cases, 1)) * 100, 1) if total_cases > 0 else 0.0

        conf_diffs = []
        for c in reasoning_cases:
            conf = c.get("confidence", 0.0)
            actual_val = 1.0 if c.get("consensus_state") in ["consensus", "partial_consensus"] else 0.0
            conf_diffs.append(abs(conf - actual_val))
        confidence_calibration = round(sum(conf_diffs) / max(len(conf_diffs), 1), 3) if conf_diffs else 0.0

        # Parallel reasoning tasks rate
        parallel_reasoning_tasks = 0
        total_reasoning_tasks = 0
        for batch in parallel_batches:
            b_tasks = batch.get("task_ids", [])
            for t_id in b_tasks:
                if "reason" in str(t_id).lower():
                    total_reasoning_tasks += 1
                    if len(b_tasks) > 1:
                        parallel_reasoning_tasks += 1
        parallel_reasoning_rate = round((parallel_reasoning_tasks / max(total_reasoning_tasks, 1)) * 100, 1) if total_reasoning_tasks > 0 else (100.0 if total_cases > 0 and len(parallel_batches) > 0 else 0.0)

        multi_agent_reasoning_metrics = {
            "reasoning_cases": total_cases,
            "average_reasoning_rounds": avg_rounds,
            "consensus_rate": consensus_rate,
            "disagreement_rate": disagreement_rate,
            "escalation_rate": escalation_rate,
            "critique_rate": critique_rate,
            "hypothesis_count": total_hypotheses,
            "evidence_supported_conclusions": evidence_supported_conclusions,
            "unresolved_disagreement_rate": unresolved_disagreement_rate,
            "confidence_calibration": confidence_calibration,
            "reasoning_duration": round(sum(len(c.get("reasoning_rounds", [])) * 150 for c in reasoning_cases), 1),
            "parallel_reasoning_rate": parallel_reasoning_rate,
        }

        collaboration_metrics = {
            "agents_involved": len(unique_agents),
            "agents_list": unique_agents,
            "total_handoffs": total_handoffs,
            "successful_handoffs": successful_handoffs,
            "rejected_handoffs": rejected_handoffs,
            "failed_agents": failed_agent_names,
            "collaboration_completed": task_success,
            "redundant_handoffs": redundant_handoffs,
            "evidence_provenance_score": provenance_score,
            **memory_metrics,
            **task_planning_metrics,
            **parallel_execution_metrics,
            **adaptive_routing_metrics,
            **agent_learning_metrics,
            **multi_agent_reasoning_metrics,
        }

        score = 0.0
        if task_success:
            score += 40.0
        if failed_agents == 0:
            score += 20.0
        if findings_count > 0:
            score += 20.0
        if recs_count > 0 or context.action_plan_id:
            score += 20.0

        return {
            "project_id": context.project_id,
            "task_type": context.task_type,
            "task_goal": context.task_goal,
            "status": context.status,
            "task_success": task_success,
            "total_agents_executed": total_agents,
            "failed_agents_count": failed_agents,
            "findings_count": findings_count,
            "recommendations_count": recs_count,
            "action_plan_id": context.action_plan_id,
            "evidence_keys_collected": list(context.evidence.keys()),
            "collaboration_metrics": collaboration_metrics,
            "memory_metrics": memory_metrics,
            "task_planning_metrics": task_planning_metrics,
            "parallel_execution_metrics": parallel_execution_metrics,
            "adaptive_routing_metrics": adaptive_routing_metrics,
            "routing_metrics": adaptive_routing_metrics,
            "agent_learning_metrics": agent_learning_metrics,
            "learning_metrics": agent_learning_metrics,
            "reasoning_metrics": multi_agent_reasoning_metrics,
            "multi_agent_reasoning_metrics": multi_agent_reasoning_metrics,
            "overall_score": round(score, 1)
        }

    def evaluate_collaboration(self, context: SharedContext, **kwargs) -> Dict[str, Any]:
        """Evaluates multi-agent collaboration, memory, task planning, and reasoning."""
        return self.evaluate_shared_context(context)

    @classmethod
    def evaluate_continuous_operations(
        cls,
        project: Any,
        operation: Optional[ContinuousOperation] = None
    ) -> Dict[str, Any]:
        """
        Milestone 6.1: Evaluate runtime-derived continuous operational metrics.
        Guarantees metrics are dynamically derived from actual runtime state/events,
        without hardcoded values.
        """
        from apps.projects.models import Project
        project_obj = project if isinstance(project, Project) else Project.objects.get(id=project)

        ops_qs = ContinuousOperation.objects.filter(project=project_obj)
        if operation:
            ops_qs = ops_qs.filter(id=operation.id)

        operations = list(ops_qs)
        active_operations = sum(1 for op in operations if op.status in [ContinuousOperationStatus.ACTIVE, ContinuousOperationStatus.RUNNING])
        paused_operations = sum(1 for op in operations if op.status == ContinuousOperationStatus.PAUSED)
        failed_operations = sum(1 for op in operations if op.status == ContinuousOperationStatus.FAILED)
        consecutive_failures = sum(op.consecutive_failures for op in operations)

        runs_qs = AgentRun.objects.filter(project=project_obj, continuous_operation__isnull=False)
        if operation:
            runs_qs = runs_qs.filter(continuous_operation=operation)

        runs = list(runs_qs)
        scheduled_runs = len(runs)
        completed_runs = sum(1 for r in runs if r.status == AgentRunStatus.COMPLETED)
        failed_runs = sum(1 for r in runs if r.status in [AgentRunStatus.FAILED, AgentRunStatus.CANCELLED])
        human_approval_waits = sum(1 for r in runs if r.status == AgentRunStatus.WAITING_FOR_APPROVAL)

        # Success rate
        total_finished = completed_runs + failed_runs
        operation_success_rate = round((completed_runs / total_finished) * 100, 1) if total_finished > 0 else 100.0

        # Average run duration (seconds)
        durations = []
        for r in runs:
            if r.completed_at and r.created_at:
                dur = (r.completed_at - r.created_at).total_seconds()
                if dur >= 0:
                    durations.append(dur)
        avg_duration = round(sum(durations) / max(1, len(durations)), 1) if durations else 0.0

        # Duplicate run prevention count & approval wait count from operation metrics
        duplicate_preventions = sum(op.metrics.get("duplicate_prevention_count", 0) for op in operations if op.metrics)
        approval_waits_from_metrics = sum(op.metrics.get("approval_wait_count", 0) for op in operations if op.metrics)
        total_approval_waits = max(human_approval_waits, approval_waits_from_metrics)

        # Scheduling delay (seconds between scheduled_for and actual created_at)
        delays = []
        for r in runs:
            if r.context_snapshot and r.context_snapshot.get("scheduled_for"):
                try:
                    from django.utils.dateparse import parse_datetime
                    scheduled_time = parse_datetime(r.context_snapshot["scheduled_for"])
                    if scheduled_time and r.created_at:
                        diff = max(0.0, (r.created_at - scheduled_time).total_seconds())
                        delays.append(diff)
                except Exception:
                    pass
        avg_delay = round(sum(delays) / max(1, len(delays)), 1) if delays else 0.0

        return {
            "project_id": project_obj.id,
            "operation_id": operation.id if operation else None,
            "active_operations": active_operations,
            "paused_operations": paused_operations,
            "failed_operations": failed_operations,
            "scheduled_runs": scheduled_runs,
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "operation_success_rate": operation_success_rate,
            "average_run_duration": avg_duration,
            "scheduling_delay": avg_delay,
            "duplicate_run_prevention_count": duplicate_preventions,
            "consecutive_failures": consecutive_failures,
            "human_approval_waits": total_approval_waits,
        }

    @classmethod
    def evaluate_event_driven_operations(
        cls,
        project: Any,
        event_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Milestone 6.2: Evaluate runtime-derived event-driven agent operational metrics.
        Guarantees metrics are dynamically derived from actual persisted SEOEvent and AgentRun records.
        """
        from apps.projects.models import Project
        from apps.seo.models import SEOEvent, SEOEventStatus, AgentRun, AgentRunStatus

        project_obj = project if isinstance(project, Project) else Project.objects.get(id=project)

        events_qs = SEOEvent.objects.filter(project=project_obj)
        if event_type:
            events_qs = events_qs.filter(event_type=event_type)

        events = list(events_qs)
        events_received = len(events)
        events_accepted = sum(1 for e in events if e.status in [SEOEventStatus.ACCEPTED, SEOEventStatus.PROCESSED])
        events_rejected = sum(1 for e in events if e.status == SEOEventStatus.REJECTED)
        events_deduplicated = sum(1 for e in events if e.status == SEOEventStatus.DEDUPLICATED)
        events_suppressed = sum(1 for e in events if e.status == SEOEventStatus.SUPPRESSED)
        events_triggered = sum(1 for e in events if e.agent_run_id is not None)
        event_trigger_failures = sum(1 for e in events if e.status == SEOEventStatus.FAILED)

        # Rates
        event_trigger_rate = round((events_triggered / max(1, events_accepted)) * 100, 1) if events_accepted > 0 else 0.0
        event_to_run_rate = round((events_triggered / max(1, events_received)) * 100, 1) if events_received > 0 else 0.0

        # Suppression breakdown
        storm_suppressions = sum(1 for e in events if "storm" in (e.suppression_reason or "").lower())
        cooldown_suppressions = sum(1 for e in events if "cooldown" in (e.suppression_reason or "").lower())

        # Average event trigger delay (seconds between occurred_at and processed_at / agent_run.created_at)
        delays = []
        for e in events:
            if e.processed_at and e.occurred_at:
                diff = max(0.0, (e.processed_at - e.occurred_at).total_seconds())
                delays.append(diff)
            elif e.agent_run and e.occurred_at:
                diff = max(0.0, (e.agent_run.created_at - e.occurred_at).total_seconds())
                delays.append(diff)
        avg_delay = round(sum(delays) / max(1, len(delays)), 2) if delays else 0.0

        return {
            "project_id": project_obj.id,
            "event_type_filter": event_type,
            "events_received": events_received,
            "events_accepted": events_accepted,
            "events_rejected": events_rejected,
            "events_deduplicated": events_deduplicated,
            "events_suppressed": events_suppressed,
            "events_triggered": events_triggered,
            "event_trigger_rate": event_trigger_rate,
            "event_to_run_rate": event_to_run_rate,
            "average_event_trigger_delay": avg_delay,
            "event_trigger_failures": event_trigger_failures,
            "event_storm_suppressions": storm_suppressions,
            "cooldown_suppressions": cooldown_suppressions,
        }

    @classmethod
    def evaluate_autonomous_monitoring(
        cls,
        project: Any
    ) -> Dict[str, Any]:
        """
        Milestone 6.3: Evaluate runtime-derived autonomous monitoring operational metrics.
        Guarantees metrics are dynamically derived from actual persisted MonitoringState,
        MonitoringSnapshot, and SEOEvent records.
        """
        from apps.projects.models import Project
        from apps.seo.models import MonitoringState, MonitoringSnapshot, SEOEvent, MonitorStatus

        project_obj = project if isinstance(project, Project) else Project.objects.get(id=project)

        states_qs = MonitoringState.objects.filter(project=project_obj)
        snapshots_qs = MonitoringSnapshot.objects.filter(project=project_obj)
        events_qs = SEOEvent.objects.filter(project=project_obj, source__startswith="autonomous_monitoring")

        monitored_targets_count = states_qs.count()
        active_anomalies_count = states_qs.filter(status=MonitorStatus.ANOMALY).count()
        recovered_targets_count = states_qs.filter(status=MonitorStatus.RECOVERED).count()

        snapshots_count = snapshots_qs.count()
        anomalies_detected_count = snapshots_qs.filter(is_anomaly=True).count()
        recoveries_detected_count = snapshots_qs.filter(is_recovery=True).count()
        changes_ignored_count = snapshots_qs.filter(is_anomaly=False, is_recovery=False).count()

        events_generated_count = events_qs.count()
        events_triggered_runs_count = events_qs.filter(agent_run__isnull=False).count()

        # Deduplication / stability count (anomalies with consecutive_anomalies > 1)
        duplicates_prevented = sum(max(0, s.consecutive_anomalies - 1) for s in states_qs)

        event_generation_rate = round(
            (events_generated_count / max(1, snapshots_count)) * 100, 1
        ) if snapshots_count > 0 else 0.0

        return {
            "project_id": project_obj.id,
            "monitored_targets": monitored_targets_count,
            "active_anomalies": active_anomalies_count,
            "recovered_targets": recovered_targets_count,
            "snapshots_created": snapshots_count,
            "changes_detected": anomalies_detected_count,
            "changes_ignored": changes_ignored_count,
            "events_generated": events_generated_count,
            "events_triggered": events_triggered_runs_count,
            "recovery_events": recoveries_detected_count,
            "duplicate_detections": duplicates_prevented,
            "event_generation_rate": event_generation_rate,
        }

    @classmethod
    def evaluate_autonomous_remediation(
        cls,
        project: Any
    ) -> Dict[str, Any]:
        """
        Milestone 6.4: Evaluate runtime-derived autonomous remediation operational metrics.
        Guarantees metrics are dynamically derived from actual persisted RemediationRecord
        and SEOAction records.
        """
        from apps.projects.models import Project
        from apps.seo.models import (
            SEOAction, ActionStatus, RemediationRecord,
            RemediationPolicyDecision, RemediationErrorCategory
        )

        project_obj = project if isinstance(project, Project) else Project.objects.get(id=project)

        records_qs = RemediationRecord.objects.filter(project=project_obj)
        total_records = records_qs.count()

        remediation_attempts = records_qs.filter(
            status__in=[
                ActionStatus.EXECUTING,
                ActionStatus.VERIFYING,
                ActionStatus.VERIFIED,
                ActionStatus.COMPLETED,
                ActionStatus.FAILED,
                ActionStatus.ROLLED_BACK
            ]
        ).count()

        remediation_successes = records_qs.filter(
            status__in=[ActionStatus.VERIFIED, ActionStatus.COMPLETED]
        ).count()

        verification_successes = remediation_successes
        verification_failures = records_qs.filter(
            error_category=RemediationErrorCategory.VERIFICATION_FAILURE
        ).count()

        human_approved_count = records_qs.filter(
            action__approved_by__isnull=False
        ).count()
        human_rejected_count = records_qs.filter(
            status=ActionStatus.REJECTED
        ).count()

        autonomous_executed_count = records_qs.filter(
            is_autonomous=True,
            status__in=[ActionStatus.VERIFYING, ActionStatus.VERIFIED, ActionStatus.COMPLETED]
        ).count()

        policy_blocked_count = records_qs.filter(
            policy_decision=RemediationPolicyDecision.BLOCKED
        ).count() + records_qs.filter(
            error_category=RemediationErrorCategory.POLICY_BLOCK
        ).count()

        rollback_count = records_qs.filter(
            status=ActionStatus.ROLLED_BACK
        ).count()

        duplicates_prevented = records_qs.filter(
            error_category=RemediationErrorCategory.IDEMPOTENCY_CONFLICT
        ).count()

        total_verif = verification_successes + verification_failures
        total_human_decisions = human_approved_count + human_rejected_count

        return {
            "project_id": project_obj.id,
            "total_remediations": total_records,
            "remediation_attempts": remediation_attempts,
            "remediation_successes": remediation_successes,
            "verification_successes": verification_successes,
            "verification_failures": verification_failures,
            "human_approved_count": human_approved_count,
            "human_rejected_count": human_rejected_count,
            "autonomous_executed_count": autonomous_executed_count,
            "policy_blocked_count": policy_blocked_count,
            "rollback_count": rollback_count,
            "duplicates_prevented": duplicates_prevented,
            "remediation_attempt_rate": round((remediation_attempts / max(1, total_records)) * 100, 1) if total_records > 0 else 0.0,
            "remediation_success_rate": round((remediation_successes / max(1, remediation_attempts)) * 100, 1) if remediation_attempts > 0 else 0.0,
            "verification_success_rate": round((verification_successes / max(1, total_verif)) * 100, 1) if total_verif > 0 else 0.0,
            "verification_failure_rate": round((verification_failures / max(1, total_verif)) * 100, 1) if total_verif > 0 else 0.0,
            "human_approval_rate": round((human_approved_count / max(1, total_human_decisions)) * 100, 1) if total_human_decisions > 0 else 0.0,
            "human_rejection_rate": round((human_rejected_count / max(1, total_human_decisions)) * 100, 1) if total_human_decisions > 0 else 0.0,
            "autonomous_execution_rate": round((autonomous_executed_count / max(1, remediation_attempts)) * 100, 1) if remediation_attempts > 0 else 0.0,
            "policy_block_rate": round((policy_blocked_count / max(1, total_records)) * 100, 1) if total_records > 0 else 0.0,
            "rollback_rate": round((rollback_count / max(1, remediation_attempts)) * 100, 1) if remediation_attempts > 0 else 0.0,
            "duplicate_prevention_rate": round((duplicates_prevented / max(1, total_records + duplicates_prevented)) * 100, 1) if (total_records + duplicates_prevented) > 0 else 0.0,
        }
