package com.aiops.api.api.event;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiException;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.common.PageResponse;
import com.aiops.api.domain.event.GeneratedEventEntity;
import com.aiops.api.domain.event.GeneratedEventRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/generated-events")
@PreAuthorize(Authorities.ANY_ROLE)
public class GeneratedEventController {

	private final GeneratedEventRepository repository;

	public GeneratedEventController(GeneratedEventRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	public ApiResponse<PageResponse<GeneratedEventDtos.Detail>> list(
			@RequestParam(required = false) String status,
			@RequestParam(defaultValue = "0") int page,
			@RequestParam(defaultValue = "50") int size) {
		int safeSize = Math.min(Math.max(size, 1), 500);
		var pageable = PageRequest.of(page, safeSize, Sort.by(Sort.Direction.DESC, "createdAt"));
		var src = repository.findAll(pageable);
		if (status != null && !status.isBlank()) {
			var list = src.getContent().stream().filter(g -> status.equalsIgnoreCase(g.getStatus())).toList();
			return ApiResponse.ok(new PageResponse<>(list.size(), page, safeSize,
					list.stream().map(GeneratedEventDtos::of).toList()));
		}
		return ApiResponse.ok(PageResponse.of(src, GeneratedEventDtos::of));
	}

	@GetMapping("/{id}")
	public ApiResponse<GeneratedEventDtos.Detail> get(@PathVariable Long id) {
		GeneratedEventEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("generated event"));
		return ApiResponse.ok(GeneratedEventDtos.of(e));
	}

	@PostMapping("/{id}/ack")
	@Transactional
	public ApiResponse<GeneratedEventDtos.Detail> ack(@PathVariable Long id) {
		GeneratedEventEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("generated event"));
		e.setStatus("acknowledged");
		return ApiResponse.ok(GeneratedEventDtos.of(repository.save(e)));
	}

	public static final class GeneratedEventDtos {

		public record Detail(Long id, Long eventTypeId, Long sourceSkillId, Long sourceRoutineCheckId,
		                     String mappedParameters, String skillConclusion, String status,
		                     java.time.OffsetDateTime createdAt) {}

		static Detail of(GeneratedEventEntity e) {
			return new Detail(e.getId(), e.getEventTypeId(), e.getSourceSkillId(),
					e.getSourceRoutineCheckId(), e.getMappedParameters(), e.getSkillConclusion(),
					e.getStatus(), e.getCreatedAt());
		}
	}
}
