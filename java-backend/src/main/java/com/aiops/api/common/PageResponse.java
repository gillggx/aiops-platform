package com.aiops.api.common;

import org.springframework.data.domain.Page;

import java.util.List;
import java.util.function.Function;

/** Envelope for paginated list responses. */
public record PageResponse<T>(long total, int page, int size, List<T> items) {

	public static <E, T> PageResponse<T> of(Page<E> src, Function<E, T> mapper) {
		return new PageResponse<>(src.getTotalElements(), src.getNumber(), src.getSize(),
				src.getContent().stream().map(mapper).toList());
	}
}
