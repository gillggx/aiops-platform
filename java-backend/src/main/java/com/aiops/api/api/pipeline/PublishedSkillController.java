package com.aiops.api.api.pipeline;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiException;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.pipeline.PublishedSkillEntity;
import com.aiops.api.domain.pipeline.PublishedSkillRepository;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

import java.time.OffsetDateTime;
import java.util.List;

@RestController
@RequestMapping("/api/v1/published-skills")
public class PublishedSkillController {

	private final PublishedSkillRepository repository;

	public PublishedSkillController(PublishedSkillRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<List<Dtos.Summary>> list(@RequestParam(required = false) String status) {
		List<PublishedSkillEntity> all = (status != null && !status.isBlank())
				? repository.findByStatus(status) : repository.findAll();
		return ApiResponse.ok(all.stream().map(Dtos::summaryOf).toList());
	}

	@GetMapping("/{id}")
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<Dtos.Detail> get(@PathVariable Long id) {
		return ApiResponse.ok(Dtos.detailOf(repository.findById(id)
				.orElseThrow(() -> ApiException.notFound("published skill"))));
	}

	@GetMapping("/by-slug/{slug}")
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<Dtos.Detail> getBySlug(@PathVariable String slug) {
		return ApiResponse.ok(Dtos.detailOf(repository.findBySlug(slug)
				.orElseThrow(() -> ApiException.notFound("published skill"))));
	}

	@PostMapping("/{id}/retire")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Dtos.Detail> retire(@PathVariable Long id) {
		PublishedSkillEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("published skill"));
		e.setStatus("retired");
		e.setRetiredAt(OffsetDateTime.now());
		return ApiResponse.ok(Dtos.detailOf(repository.save(e)));
	}

	public static final class Dtos {

		public record Summary(Long id, Long pipelineId, String pipelineVersion, String slug,
		                      String name, String status, OffsetDateTime publishedAt) {}

		public record Detail(Long id, Long pipelineId, String pipelineVersion, String slug, String name,
		                     String useCase, String whenToUse, String inputsSchema, String outputsSchema,
		                     String exampleInvocation, String tags, String status, String publishedBy,
		                     OffsetDateTime publishedAt, OffsetDateTime retiredAt) {}

		static Summary summaryOf(PublishedSkillEntity e) {
			return new Summary(e.getId(), e.getPipelineId(), e.getPipelineVersion(), e.getSlug(),
					e.getName(), e.getStatus(), e.getPublishedAt());
		}

		static Detail detailOf(PublishedSkillEntity e) {
			return new Detail(e.getId(), e.getPipelineId(), e.getPipelineVersion(), e.getSlug(),
					e.getName(), e.getUseCase(), e.getWhenToUse(), e.getInputsSchema(),
					e.getOutputsSchema(), e.getExampleInvocation(), e.getTags(),
					e.getStatus(), e.getPublishedBy(), e.getPublishedAt(), e.getRetiredAt());
		}
	}
}
