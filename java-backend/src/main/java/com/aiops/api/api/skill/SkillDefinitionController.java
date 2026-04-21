package com.aiops.api.api.skill;

import com.aiops.api.auth.AuthPrincipal;
import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiException;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.skill.SkillDefinitionEntity;
import com.aiops.api.domain.skill.SkillDefinitionRepository;
import jakarta.validation.constraints.NotBlank;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/v1/skills")
public class SkillDefinitionController {

	private final SkillDefinitionRepository repository;

	public SkillDefinitionController(SkillDefinitionRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<List<SkillDtos.Summary>> list(@RequestParam(required = false) String source,
	                                                 @RequestParam(required = false) Boolean active) {
		List<SkillDefinitionEntity> all = (source != null && !source.isBlank())
				? repository.findBySource(source)
				: repository.findAll();
		var stream = all.stream();
		if (Boolean.TRUE.equals(active)) stream = stream.filter(s -> Boolean.TRUE.equals(s.getIsActive()));
		return ApiResponse.ok(stream.map(SkillDtos::summaryOf).toList());
	}

	@GetMapping("/{id}")
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<SkillDtos.Detail> get(@PathVariable Long id) {
		SkillDefinitionEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("skill"));
		return ApiResponse.ok(SkillDtos.detailOf(e));
	}

	@PostMapping
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<SkillDtos.Detail> create(@Validated @RequestBody SkillDtos.CreateRequest req,
	                                            @AuthenticationPrincipal AuthPrincipal caller) {
		if (repository.findByName(req.name()).isPresent()) {
			throw ApiException.conflict("skill name already exists");
		}
		SkillDefinitionEntity e = new SkillDefinitionEntity();
		e.setName(req.name());
		e.setDescription(req.description() == null ? "" : req.description());
		if (req.triggerMode() != null) e.setTriggerMode(req.triggerMode());
		if (req.source() != null) e.setSource(req.source());
		if (req.visibility() != null) e.setVisibility(req.visibility());
		if (req.stepsMapping() != null) e.setStepsMapping(req.stepsMapping());
		if (req.inputSchema() != null) e.setInputSchema(req.inputSchema());
		if (req.outputSchema() != null) e.setOutputSchema(req.outputSchema());
		if (req.pipelineConfig() != null) e.setPipelineConfig(req.pipelineConfig());
		if (req.bindingType() != null) e.setBindingType(req.bindingType());
		if (req.autoCheckDescription() != null) e.setAutoCheckDescription(req.autoCheckDescription());
		e.setCreatedBy(caller.userId());
		return ApiResponse.ok(SkillDtos.detailOf(repository.save(e)));
	}

	@PutMapping("/{id}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<SkillDtos.Detail> update(@PathVariable Long id,
	                                            @Validated @RequestBody SkillDtos.UpdateRequest req) {
		SkillDefinitionEntity e = repository.findById(id).orElseThrow(() -> ApiException.notFound("skill"));
		if (req.description() != null) e.setDescription(req.description());
		if (req.triggerMode() != null) e.setTriggerMode(req.triggerMode());
		if (req.visibility() != null) e.setVisibility(req.visibility());
		if (req.stepsMapping() != null) e.setStepsMapping(req.stepsMapping());
		if (req.inputSchema() != null) e.setInputSchema(req.inputSchema());
		if (req.outputSchema() != null) e.setOutputSchema(req.outputSchema());
		if (req.pipelineConfig() != null) e.setPipelineConfig(req.pipelineConfig());
		if (req.autoCheckDescription() != null) e.setAutoCheckDescription(req.autoCheckDescription());
		if (req.isActive() != null) e.setIsActive(req.isActive());
		return ApiResponse.ok(SkillDtos.detailOf(repository.save(e)));
	}

	@DeleteMapping("/{id}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN_OR_PE)
	public ApiResponse<Void> delete(@PathVariable Long id) {
		if (!repository.existsById(id)) throw ApiException.notFound("skill");
		repository.deleteById(id);
		return ApiResponse.ok(null);
	}

	public static final class SkillDtos {

		public record Summary(Long id, String name, String description, String source,
		                      String triggerMode, String visibility, Boolean isActive,
		                      java.time.OffsetDateTime updatedAt) {}

		public record Detail(Long id, String name, String description, Long triggerEventId,
		                     String triggerMode, String stepsMapping, String inputSchema,
		                     String outputSchema, String pipelineConfig, String source,
		                     String bindingType, String autoCheckDescription, String visibility,
		                     Long triggerPatrolId, Long createdBy, Boolean isActive,
		                     java.time.OffsetDateTime createdAt, java.time.OffsetDateTime updatedAt) {}

		public record CreateRequest(@NotBlank String name, String description, String triggerMode,
		                            String source, String visibility, String stepsMapping,
		                            String inputSchema, String outputSchema, String pipelineConfig,
		                            String bindingType, String autoCheckDescription) {}

		public record UpdateRequest(String description, String triggerMode, String visibility,
		                            String stepsMapping, String inputSchema, String outputSchema,
		                            String pipelineConfig, String autoCheckDescription, Boolean isActive) {}

		static Summary summaryOf(SkillDefinitionEntity e) {
			return new Summary(e.getId(), e.getName(), e.getDescription(), e.getSource(),
					e.getTriggerMode(), e.getVisibility(), e.getIsActive(), e.getUpdatedAt());
		}

		static Detail detailOf(SkillDefinitionEntity e) {
			return new Detail(e.getId(), e.getName(), e.getDescription(), e.getTriggerEventId(),
					e.getTriggerMode(), e.getStepsMapping(), e.getInputSchema(),
					e.getOutputSchema(), e.getPipelineConfig(), e.getSource(),
					e.getBindingType(), e.getAutoCheckDescription(), e.getVisibility(),
					e.getTriggerPatrolId(), e.getCreatedBy(), e.getIsActive(),
					e.getCreatedAt(), e.getUpdatedAt());
		}
	}
}
