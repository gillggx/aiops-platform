package com.aiops.api.api.agent;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.agent.AgentExperienceMemoryEntity;
import com.aiops.api.domain.agent.AgentExperienceMemoryRepository;
import com.aiops.api.domain.agent.AgentMemoryEntity;
import com.aiops.api.domain.agent.AgentMemoryRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Public read-only path aliases the Frontend memory page uses:
 *   GET /api/v1/agent/memory       — legacy agent_memories (RAG)
 *   GET /api/v1/experience-memory  — agent_experience_memory
 *   GET /api/v1/agent-memories     — probe path
 * Returns {memories: [...]} for legacy compat with Python.
 */
@RestController
@PreAuthorize(Authorities.ANY_ROLE)
public class AgentMemoryAliasController {

	private final AgentMemoryRepository memRepo;
	private final AgentExperienceMemoryRepository expRepo;

	public AgentMemoryAliasController(AgentMemoryRepository memRepo,
	                                  AgentExperienceMemoryRepository expRepo) {
		this.memRepo = memRepo;
		this.expRepo = expRepo;
	}

	@GetMapping({"/api/v1/agent/memory", "/api/v1/agent-memories"})
	public Map<String, Object> listLegacy(@RequestParam(required = false) Long userId,
	                                      @RequestParam(defaultValue = "100") int limit) {
		int safe = Math.min(Math.max(limit, 1), 500);
		List<AgentMemoryEntity> rows;
		if (userId != null && userId > 0) {
			rows = memRepo.findByUserIdOrderByCreatedAtDesc(userId);
		} else {
			rows = memRepo.findAll(PageRequest.of(0, safe,
					org.springframework.data.domain.Sort.by(
							org.springframework.data.domain.Sort.Direction.DESC, "createdAt"))).getContent();
		}
		List<Map<String, Object>> items = rows.stream().limit(safe).map(m -> {
			Map<String, Object> r = new java.util.HashMap<>();
			r.put("id", m.getId());
			r.put("user_id", m.getUserId());
			r.put("content", m.getContent());
			r.put("source", m.getSource());
			r.put("ref_id", m.getRefId());
			r.put("task_type", m.getTaskType());
			r.put("data_subject", m.getDataSubject());
			r.put("tool_name", m.getToolName());
			r.put("created_at", m.getCreatedAt());
			return r;
		}).toList();
		return Map.of("memories", items);
	}

	@GetMapping("/api/v1/experience-memory")
	public ApiResponse<List<Map<String, Object>>> listExperience(
			@RequestParam(defaultValue = "100") int limit) {
		int safe = Math.min(Math.max(limit, 1), 500);
		var page = PageRequest.of(0, safe,
				org.springframework.data.domain.Sort.by(
						org.springframework.data.domain.Sort.Direction.DESC, "createdAt"));
		List<Map<String, Object>> items = expRepo.findAll(page).getContent().stream().map(e -> {
			Map<String, Object> r = new java.util.HashMap<>();
			r.put("id", e.getId());
			r.put("user_id", e.getUserId());
			r.put("intent_summary", e.getIntentSummary());
			r.put("abstract_action", e.getAbstractAction());
			r.put("confidence_score", e.getConfidenceScore());
			r.put("use_count", e.getUseCount());
			r.put("success_count", e.getSuccessCount());
			r.put("fail_count", e.getFailCount());
			r.put("status", e.getStatus());
			r.put("source", e.getSource());
			r.put("last_used_at", e.getLastUsedAt());
			r.put("created_at", e.getCreatedAt());
			return r;
		}).toList();
		return ApiResponse.ok(items);
	}
}
