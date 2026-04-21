package com.aiops.api.api.skill;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiException;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.skill.ScriptVersionEntity;
import com.aiops.api.domain.skill.ScriptVersionRepository;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.time.OffsetDateTime;
import java.util.List;

/** Script version registry — read by all roles, write by PE+IT_ADMIN. */
@RestController
@RequestMapping("/api/v1/script-versions")
public class ScriptVersionController {

	private final ScriptVersionRepository repository;

	public ScriptVersionController(ScriptVersionRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<List<Dtos.Summary>> list(@RequestParam Long skillId) {
		return ApiResponse.ok(repository.findBySkillIdOrderByVersionDesc(skillId)
				.stream().map(Dtos::summaryOf).toList());
	}

	@GetMapping("/{id}")
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<Dtos.Detail> get(@PathVariable Long id) {
		return ApiResponse.ok(Dtos.detailOf(repository.findById(id)
				.orElseThrow(() -> ApiException.notFound("script version"))));
	}

	@PostMapping
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Dtos.Detail> create(@Validated @RequestBody Dtos.CreateRequest req) {
		ScriptVersionEntity e = new ScriptVersionEntity();
		e.setSkillId(req.skillId());
		e.setCode(req.code());
		if (req.version() != null) e.setVersion(req.version());
		if (req.changeNote() != null) e.setChangeNote(req.changeNote());
		return ApiResponse.ok(Dtos.detailOf(repository.save(e)));
	}

	@PostMapping("/{id}/approve")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Dtos.Detail> approve(@PathVariable Long id, @RequestParam String reviewer) {
		ScriptVersionEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("script version"));
		e.setStatus("approved");
		e.setReviewedBy(reviewer);
		e.setApprovedAt(OffsetDateTime.now());
		return ApiResponse.ok(Dtos.detailOf(repository.save(e)));
	}

	public static final class Dtos {
		public record Summary(Long id, Long skillId, Integer version, String status,
		                      String reviewedBy, OffsetDateTime approvedAt,
		                      OffsetDateTime generatedAt) {}

		public record Detail(Long id, Long skillId, Integer version, String status, String code,
		                     String changeNote, String reviewedBy,
		                     OffsetDateTime approvedAt, OffsetDateTime generatedAt) {}

		public record CreateRequest(@NotNull Long skillId, @NotBlank String code,
		                            Integer version, String changeNote) {}

		static Summary summaryOf(ScriptVersionEntity e) {
			return new Summary(e.getId(), e.getSkillId(), e.getVersion(), e.getStatus(),
					e.getReviewedBy(), e.getApprovedAt(), e.getGeneratedAt());
		}

		static Detail detailOf(ScriptVersionEntity e) {
			return new Detail(e.getId(), e.getSkillId(), e.getVersion(), e.getStatus(),
					e.getCode(), e.getChangeNote(), e.getReviewedBy(),
					e.getApprovedAt(), e.getGeneratedAt());
		}
	}
}
