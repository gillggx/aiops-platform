package com.aiops.api.api.aiops;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.alarm.AlarmEntity;
import com.aiops.api.domain.alarm.AlarmRepository;
import com.aiops.api.domain.event.GeneratedEventEntity;
import com.aiops.api.domain.event.GeneratedEventRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

/**
 * Dashboard briefing — quick aggregate view for on-duty users.
 * Rich analytics (LLM-generated summary) comes from the Python sidecar via
 * {@code /api/v1/agent/briefing}; this controller only returns the raw counts
 * the Frontend top bar needs for fast load.
 */
@RestController
@RequestMapping("/api/v1/briefing")
@PreAuthorize(Authorities.ANY_ROLE)
public class BriefingController {

	private final AlarmRepository alarmRepo;
	private final GeneratedEventRepository eventRepo;

	public BriefingController(AlarmRepository alarmRepo, GeneratedEventRepository eventRepo) {
		this.alarmRepo = alarmRepo;
		this.eventRepo = eventRepo;
	}

	@GetMapping
	public ApiResponse<Map<String, Object>> summary(@RequestParam(defaultValue = "10") int recent) {
		int safeRecent = Math.max(1, Math.min(recent, 50));

		List<AlarmEntity> activeAlarms = alarmRepo.findByStatusOrderByCreatedAtDesc("active");
		List<AlarmEntity> recentAlarms = alarmRepo
				.findAll(PageRequest.of(0, safeRecent, Sort.by(Sort.Direction.DESC, "createdAt")))
				.getContent();
		List<GeneratedEventEntity> recentEvents = eventRepo
				.findAll(PageRequest.of(0, safeRecent, Sort.by(Sort.Direction.DESC, "createdAt")))
				.getContent();
		long pendingEvents = eventRepo.findByStatus("pending").size();

		return ApiResponse.ok(Map.of(
				"generated_at", OffsetDateTime.now(),
				"alarms", Map.of(
						"active", activeAlarms.size(),
						"recent", recentAlarms.stream().map(a -> Map.of(
								"id", a.getId(),
								"severity", a.getSeverity(),
								"title", a.getTitle(),
								"status", a.getStatus(),
								"created_at", a.getCreatedAt()
						)).toList()
				),
				"events", Map.of(
						"pending", pendingEvents,
						"recent", recentEvents.stream().map(e -> Map.of(
								"id", e.getId(),
								"event_type_id", e.getEventTypeId(),
								"status", e.getStatus(),
								"created_at", e.getCreatedAt()
						)).toList()
				)
		));
	}
}
