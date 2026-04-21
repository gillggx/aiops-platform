package com.aiops.api.api.skill;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiException;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.skill.CronJobEntity;
import com.aiops.api.domain.skill.CronJobRepository;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/cron-jobs")
public class CronJobController {

	private final CronJobRepository repository;

	public CronJobController(CronJobRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<List<Dtos.Detail>> list(@RequestParam(required = false) String status) {
		List<CronJobEntity> all = (status != null && !status.isBlank())
				? repository.findByStatus(status) : repository.findAll();
		return ApiResponse.ok(all.stream().map(Dtos::of).toList());
	}

	@GetMapping("/{id}")
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<Dtos.Detail> get(@PathVariable Long id) {
		return ApiResponse.ok(Dtos.of(repository.findById(id)
				.orElseThrow(() -> ApiException.notFound("cron job"))));
	}

	@PostMapping
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Dtos.Detail> create(@Validated @RequestBody Dtos.CreateRequest req) {
		CronJobEntity e = new CronJobEntity();
		e.setSkillId(req.skillId());
		e.setSchedule(req.schedule());
		if (req.timezone() != null) e.setTimezone(req.timezone());
		if (req.label() != null) e.setLabel(req.label());
		if (req.createdBy() != null) e.setCreatedBy(req.createdBy());
		return ApiResponse.ok(Dtos.of(repository.save(e)));
	}

	@PutMapping("/{id}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Dtos.Detail> update(@PathVariable Long id,
	                                       @Validated @RequestBody Dtos.UpdateRequest req) {
		CronJobEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("cron job"));
		if (req.schedule() != null) e.setSchedule(req.schedule());
		if (req.timezone() != null) e.setTimezone(req.timezone());
		if (req.label() != null) e.setLabel(req.label());
		if (req.status() != null) e.setStatus(req.status());
		return ApiResponse.ok(Dtos.of(repository.save(e)));
	}

	@DeleteMapping("/{id}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Void> delete(@PathVariable Long id) {
		if (!repository.existsById(id)) throw ApiException.notFound("cron job");
		repository.deleteById(id);
		return ApiResponse.ok(null);
	}

	public static final class Dtos {

		public record Detail(Long id, Long skillId, String schedule, String timezone, String label,
		                     String status, String createdBy,
		                     java.time.OffsetDateTime lastRunAt, java.time.OffsetDateTime nextRunAt,
		                     java.time.OffsetDateTime createdAt, java.time.OffsetDateTime updatedAt) {}

		public record CreateRequest(@NotNull Long skillId, @NotBlank String schedule,
		                            String timezone, String label, String createdBy) {}

		public record UpdateRequest(String schedule, String timezone, String label, String status) {}

		static Detail of(CronJobEntity e) {
			return new Detail(e.getId(), e.getSkillId(), e.getSchedule(), e.getTimezone(),
					e.getLabel(), e.getStatus(), e.getCreatedBy(),
					e.getLastRunAt(), e.getNextRunAt(), e.getCreatedAt(), e.getUpdatedAt());
		}
	}
}
