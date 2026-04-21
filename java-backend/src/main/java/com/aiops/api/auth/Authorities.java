package com.aiops.api.auth;

/** Convenience role-expression constants for use in {@code @PreAuthorize}. */
public final class Authorities {

	private Authorities() {}

	public static final String ADMIN = "hasRole('IT_ADMIN')";
	public static final String PE = "hasRole('PE')";
	public static final String ON_DUTY = "hasRole('ON_DUTY')";

	public static final String ADMIN_OR_PE = "hasAnyRole('IT_ADMIN','PE')";
	public static final String ANY_ROLE = "hasAnyRole('IT_ADMIN','PE','ON_DUTY')";
}
