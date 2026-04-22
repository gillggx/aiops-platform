package com.aiops.api.api.skill;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.skill.SkillDefinitionEntity;
import com.aiops.api.domain.skill.SkillDefinitionRepository;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Python legacy path. Frontend's {@code /api/admin/skills} still proxies to
 * {@code /api/v1/skill-definitions}. Alias it to the same list of skills so we
 * don't need a Frontend redeploy.
 */
@RestController
@RequestMapping("/api/v1/skill-definitions")
@PreAuthorize(Authorities.ANY_ROLE)
public class SkillDefinitionsAliasController {

	private final SkillDefinitionRepository repository;

	public SkillDefinitionsAliasController(SkillDefinitionRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	public ApiResponse<List<SkillDefinitionEntity>> list(@RequestParam(required = false) String source) {
		List<SkillDefinitionEntity> all = (source != null && !source.isBlank())
				? repository.findBySource(source)
				: repository.findAll();
		return ApiResponse.ok(all);
	}

	@GetMapping("/{id}")
	public ApiResponse<SkillDefinitionEntity> get(@PathVariable Long id) {
		return ApiResponse.ok(repository.findById(id).orElseThrow(() ->
				new com.aiops.api.common.ApiException(
						org.springframework.http.HttpStatus.NOT_FOUND,
						"not_found", "skill not found")));
	}
}
