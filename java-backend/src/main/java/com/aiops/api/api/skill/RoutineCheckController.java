package com.aiops.api.api.skill;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiException;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.skill.RoutineCheckEntity;
import com.aiops.api.domain.skill.RoutineCheckRepository;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/routine-checks")
public class RoutineCheckController {

	private final RoutineCheckRepository repository;

	public RoutineCheckController(RoutineCheckRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<List<Dtos.Detail>> list(@RequestParam(required = false) Boolean active,
	                                           @RequestParam(required = false) Long skillId) {
		List<RoutineCheckEntity> all;
		if (skillId != null) all = repository.findBySkillId(skillId);
		else if (Boolean.TRUE.equals(active)) all = repository.findByIsActiveTrue();
		else all = repository.findAll();
		return ApiResponse.ok(all.stream().map(Dtos::of).toList());
	}

	@GetMapping("/{id}")
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<Dtos.Detail> get(@PathVariable Long id) {
		return ApiResponse.ok(Dtos.of(repository.findById(id)
				.orElseThrow(() -> ApiException.notFound("routine check"))));
	}

	@PostMapping
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Dtos.Detail> create(@Validated @RequestBody Dtos.CreateRequest req) {
		RoutineCheckEntity e = new RoutineCheckEntity();
		e.setName(req.name());
		e.setSkillId(req.skillId());
		if (req.skillInput() != null) e.setSkillInput(req.skillInput());
		if (req.triggerEventId() != null) e.setTriggerEventId(req.triggerEventId());
		if (req.scheduleInterval() != null) e.setScheduleInterval(req.scheduleInterval());
		if (req.scheduleTime() != null) e.setScheduleTime(req.scheduleTime());
		if (req.eventParamMappings() != null) e.setEventParamMappings(req.eventParamMappings());
		return ApiResponse.ok(Dtos.of(repository.save(e)));
	}

	@PutMapping("/{id}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Dtos.Detail> update(@PathVariable Long id,
	                                       @Validated @RequestBody Dtos.UpdateRequest req) {
		RoutineCheckEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("routine check"));
		if (req.skillInput() != null) e.setSkillInput(req.skillInput());
		if (req.scheduleInterval() != null) e.setScheduleInterval(req.scheduleInterval());
		if (req.scheduleTime() != null) e.setScheduleTime(req.scheduleTime());
		if (req.isActive() != null) e.setIsActive(req.isActive());
		if (req.eventParamMappings() != null) e.setEventParamMappings(req.eventParamMappings());
		return ApiResponse.ok(Dtos.of(repository.save(e)));
	}

	@DeleteMapping("/{id}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Void> delete(@PathVariable Long id) {
		if (!repository.existsById(id)) throw ApiException.notFound("routine check");
		repository.deleteById(id);
		return ApiResponse.ok(null);
	}

	public static final class Dtos {

		public record Detail(Long id, String name, Long skillId, String skillInput, Long triggerEventId,
		                     String eventParamMappings, String scheduleInterval, String scheduleTime,
		                     Boolean isActive, String lastRunAt, String lastRunStatus, String expireAt,
		                     java.time.OffsetDateTime createdAt, java.time.OffsetDateTime updatedAt) {}

		public record CreateRequest(@NotBlank String name, @NotNull Long skillId, String skillInput,
		                            Long triggerEventId, String scheduleInterval,
		                            String scheduleTime, String eventParamMappings) {}

		public record UpdateRequest(String skillInput, String scheduleInterval, String scheduleTime,
		                            Boolean isActive, String eventParamMappings) {}

		static Detail of(RoutineCheckEntity e) {
			return new Detail(e.getId(), e.getName(), e.getSkillId(), e.getSkillInput(),
					e.getTriggerEventId(), e.getEventParamMappings(), e.getScheduleInterval(),
					e.getScheduleTime(), e.getIsActive(), e.getLastRunAt(), e.getLastRunStatus(),
					e.getExpireAt(), e.getCreatedAt(), e.getUpdatedAt());
		}
	}
}
