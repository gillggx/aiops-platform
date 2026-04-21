package com.aiops.api.api.admin;

import com.aiops.api.auth.Authorities;
import com.aiops.api.common.ApiException;
import com.aiops.api.common.ApiResponse;
import com.aiops.api.domain.system.SystemParameterEntity;
import com.aiops.api.domain.system.SystemParameterRepository;
import jakarta.validation.constraints.NotBlank;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/** Platform-wide key/value parameters — readable to all, writable by IT_ADMIN only. */
@RestController
@RequestMapping("/api/v1/system-parameters")
public class SystemParameterController {

	private final SystemParameterRepository repository;

	public SystemParameterController(SystemParameterRepository repository) {
		this.repository = repository;
	}

	@GetMapping
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<List<Dtos.Detail>> list() {
		return ApiResponse.ok(repository.findAll().stream().map(Dtos::of).toList());
	}

	@GetMapping("/{key}")
	@PreAuthorize(Authorities.ANY_ROLE)
	public ApiResponse<Dtos.Detail> get(@PathVariable String key) {
		SystemParameterEntity e = repository.findByKey(key)
				.orElseThrow(() -> ApiException.notFound("system parameter"));
		return ApiResponse.ok(Dtos.of(e));
	}

	@PutMapping("/{key}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN)
	public ApiResponse<Dtos.Detail> upsert(@PathVariable String key,
	                                       @Validated @RequestBody Dtos.UpsertRequest req) {
		SystemParameterEntity e = repository.findByKey(key).orElseGet(() -> {
			SystemParameterEntity n = new SystemParameterEntity();
			n.setKey(key);
			return n;
		});
		e.setValue(req.value());
		if (req.description() != null) e.setDescription(req.description());
		return ApiResponse.ok(Dtos.of(repository.save(e)));
	}

	@DeleteMapping("/{key}")
	@Transactional
	@PreAuthorize(Authorities.ADMIN)
	public ApiResponse<Void> delete(@PathVariable String key) {
		SystemParameterEntity e = repository.findByKey(key)
				.orElseThrow(() -> ApiException.notFound("system parameter"));
		repository.delete(e);
		return ApiResponse.ok(null);
	}

	public static final class Dtos {

		public record Detail(Long id, String key, String value, String description,
		                     java.time.OffsetDateTime updatedAt) {}

		public record UpsertRequest(@NotBlank String value, String description) {}

		static Detail of(SystemParameterEntity e) {
			return new Detail(e.getId(), e.getKey(), e.getValue(), e.getDescription(), e.getUpdatedAt());
		}
	}
}
