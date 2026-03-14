"""
Authentication UI Components
============================

Reusable components for user registration and login.
Uses semantic HTML with Tailwind + MonsterUI styling.

Version: 2.0.0
Date: 2025-12-02
"""

from fasthtml.common import NotStr


class AuthComponents:
    """Reusable component library for authentication interface"""

    @staticmethod
    def render_login_page(error_message: str | None = None) -> NotStr:
        """
        Render the login page with dark theme centered design.

        Args:
            error_message: Optional error message to display

        Returns:
            Complete login page UI as NotStr (full HTML document)
        """
        error_html = ""
        if error_message:
            error_html = f"""
            <div class="mb-4 rounded-md bg-red-500/10 border border-red-500/20 p-3">
                <p class="text-sm text-red-400">{error_message}</p>
            </div>
            """

        return NotStr(f"""<!DOCTYPE html>
<html class="h-full dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign In | SKUEL</title>
    <link rel="stylesheet" href="/static/css/output.css?v=4">
</head>
<body class="h-full bg-secondary">
    <div class="flex min-h-full flex-col justify-center px-6 py-12 lg:px-8">
        <div class="sm:mx-auto sm:w-full sm:max-w-sm">
            <h1 class="text-center text-3xl font-bold text-primary">SKUEL</h1>
            <h2 class="mt-10 text-center text-2xl/9 font-bold tracking-tight text-foreground">Sign in to your account</h2>
        </div>

        <div class="mt-10 sm:mx-auto sm:w-full sm:max-w-sm">
            {error_html}

            <form id="login-form" action="/login/submit" method="POST" class="space-y-6">
                <div>
                    <label for="username" class="block text-sm/6 font-medium text-foreground">Email address</label>
                    <div class="mt-2">
                        <input
                            id="username"
                            type="text"
                            name="username"
                            required
                            autocomplete="email"
                            autofocus
                            class="uk-input w-full"
                        />
                    </div>
                </div>

                <div>
                    <div class="flex items-center justify-between">
                        <label for="password" class="block text-sm/6 font-medium text-foreground">Password</label>
                        <div class="text-sm">
                            <a href="/forgot-password" class="font-semibold text-primary/80 hover:text-primary">Forgot password?</a>
                        </div>
                    </div>
                    <div class="mt-2">
                        <input
                            id="password"
                            type="password"
                            name="password"
                            required
                            autocomplete="current-password"
                            class="uk-input w-full"
                        />
                    </div>
                </div>

                <div>
                    <button type="submit" class="flex w-full justify-center rounded-md bg-primary px-3 py-1.5 text-sm/6 font-semibold text-primary-foreground hover:bg-primary/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">Sign in</button>
                </div>
            </form>

            <p class="mt-10 text-center text-sm/6 text-muted-foreground">
                Not a member?
                <a href="/register" class="font-semibold text-primary/80 hover:text-primary">Create an account</a>
            </p>

        </div>
    </div>
</body>
</html>""")

    @staticmethod
    def render_registration_page(error_message: str | None = None) -> NotStr:
        """
        Render the registration page with dark theme centered design.

        Matches the login page styling for visual consistency.

        Args:
            error_message: Optional error message to display

        Returns:
            Complete registration page UI as NotStr (full HTML document)
        """
        error_html = ""
        if error_message:
            error_html = f"""
            <div class="mb-4 rounded-md bg-red-500/10 border border-red-500/20 p-3">
                <p class="text-sm text-red-400">{error_message}</p>
            </div>
            """

        return NotStr(f"""<!DOCTYPE html>
<html class="h-full dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create Account | SKUEL</title>
    <link rel="stylesheet" href="/static/css/output.css?v=4">
</head>
<body class="h-full bg-secondary">
    <div class="flex min-h-full flex-col justify-center px-6 py-12 lg:px-8">
        <div class="sm:mx-auto sm:w-full sm:max-w-sm">
            <h1 class="text-center text-3xl font-bold text-primary">SKUEL</h1>
            <h2 class="mt-8 text-center text-2xl/9 font-bold tracking-tight text-foreground">Create your account</h2>
            <p class="mt-2 text-center text-sm text-muted-foreground">Start your learning journey</p>
        </div>

        <div class="mt-8 sm:mx-auto sm:w-full sm:max-w-sm">
            {error_html}

            <form action="/register/submit" method="POST" class="space-y-5">
                <!-- Username field -->
                <div>
                    <label for="username" class="block text-sm/6 font-medium text-foreground">Username</label>
                    <div class="mt-2">
                        <input
                            id="username"
                            type="text"
                            name="username"
                            placeholder="Choose a username"
                            required
                            autofocus
                            minlength="3"
                            maxlength="30"
                            pattern="[a-zA-Z0-9_]+"
                            class="uk-input w-full"
                        />
                    </div>
                    <p class="mt-1 text-xs text-muted-foreground">3-30 characters, letters, numbers, and underscores only</p>
                </div>

                <!-- Email field -->
                <div>
                    <label for="email" class="block text-sm/6 font-medium text-foreground">Email address</label>
                    <div class="mt-2">
                        <input
                            id="email"
                            type="email"
                            name="email"
                            placeholder="your.email@example.com"
                            required
                            autocomplete="email"
                            class="uk-input w-full"
                        />
                    </div>
                </div>

                <!-- Display name field -->
                <div>
                    <label for="display_name" class="block text-sm/6 font-medium text-foreground">Display name</label>
                    <div class="mt-2">
                        <input
                            id="display_name"
                            type="text"
                            name="display_name"
                            placeholder="How should we call you?"
                            required
                            maxlength="100"
                            class="uk-input w-full"
                        />
                    </div>
                </div>

                <!-- Password field -->
                <div>
                    <label for="password" class="block text-sm/6 font-medium text-foreground">Password</label>
                    <div class="mt-2">
                        <input
                            id="password"
                            type="password"
                            name="password"
                            placeholder="Create a strong password"
                            required
                            minlength="6"
                            autocomplete="new-password"
                            class="uk-input w-full"
                        />
                    </div>
                    <p class="mt-1 text-xs text-muted-foreground">At least 6 characters</p>
                </div>

                <!-- Confirm password field -->
                <div>
                    <label for="confirm_password" class="block text-sm/6 font-medium text-foreground">Confirm password</label>
                    <div class="mt-2">
                        <input
                            id="confirm_password"
                            type="password"
                            name="confirm_password"
                            placeholder="Re-enter your password"
                            required
                            minlength="6"
                            autocomplete="new-password"
                            class="uk-input w-full"
                        />
                    </div>
                </div>

                <!-- Terms acceptance -->
                <div class="flex items-start gap-3">
                    <input type="hidden" name="accept_terms" value="0" />
                    <input
                        type="checkbox"
                        id="accept_terms"
                        name="accept_terms"
                        value="1"
                        required
                        class="uk-checkbox mt-1 h-4 w-4"
                    />
                    <label for="accept_terms" class="text-sm text-muted-foreground">
                        I agree to the
                        <a href="/terms" class="font-semibold text-primary/80 hover:text-primary">Terms of Service</a>
                        and
                        <a href="/privacy" class="font-semibold text-primary/80 hover:text-primary">Privacy Policy</a>
                    </label>
                </div>

                <!-- Submit button -->
                <div class="pt-2">
                    <button type="submit" class="flex w-full justify-center rounded-md bg-primary px-3 py-1.5 text-sm/6 font-semibold text-primary-foreground hover:bg-primary/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
                        Create account
                    </button>
                </div>
            </form>

            <p class="mt-8 text-center text-sm/6 text-muted-foreground">
                Already have an account?
                <a href="/login" class="font-semibold text-primary/80 hover:text-primary">Sign in</a>
            </p>
        </div>
    </div>
</body>
</html>""")

    @staticmethod
    def render_registration_success(username: str) -> NotStr:
        """
        Render registration success page.

        Args:
            username: The newly registered username

        Returns:
            Success message UI as NotStr
        """
        return NotStr(f"""
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-lg w-full">
                <div class="uk-card-body text-center">
                    <div class="text-6xl mb-4">✅</div>
                    <h1 class="uk-card-title text-3xl font-bold justify-center mb-2">Welcome to SKUEL!</h1>
                    <p class="text-lg text-muted-foreground mb-6">
                        Your account '{username}' has been created successfully!
                    </p>

                    <div class="text-left mb-6">
                        <h3 class="text-xl font-semibold mb-4">What's Next?</h3>
                        <ul class="space-y-2 text-foreground/80">
                            <li class="flex items-center gap-2">
                                <span>📚</span> Explore learning paths
                            </li>
                            <li class="flex items-center gap-2">
                                <span>✅</span> Create your first task
                            </li>
                            <li class="flex items-center gap-2">
                                <span>🎯</span> Set your goals
                            </li>
                            <li class="flex items-center gap-2">
                                <span>⚙️</span> Customize your preferences
                            </li>
                        </ul>
                    </div>

                    <div class="uk-card-footer justify-center">
                        <a href="/" class="uk-btn uk-btn-primary w-full">Get Started</a>
                    </div>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_login_error(error_message: str) -> NotStr:
        """
        Render login error page.

        Args:
            error_message: The error message to display

        Returns:
            Error page UI as NotStr
        """
        return NotStr(f"""
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-lg w-full">
                <div class="uk-card-body text-center">
                    <div class="text-6xl mb-4">❌</div>
                    <h1 class="uk-card-title text-3xl font-bold text-destructive justify-center mb-2">
                        Login Failed
                    </h1>
                    <p class="text-lg text-foreground/80 mb-6">{error_message}</p>

                    <div class="uk-card-footer justify-center gap-3">
                        <a href="/login" class="uk-btn uk-btn-primary">Try Again</a>
                        <a href="/forgot-password" class="uk-btn uk-btn-secondary">Forgot Password?</a>
                    </div>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_forgot_password_form(error_message: str | None = None) -> NotStr:
        """
        Render forgot password email form.

        Args:
            error_message: Optional error message to display

        Returns:
            Forgot password form UI as NotStr
        """
        error_html = ""
        if error_message:
            error_html = f"""
            <div class="mb-4 rounded-md bg-red-500/10 border border-red-500/20 p-3">
                <p class="text-sm text-red-400">{error_message}</p>
            </div>
            """

        return NotStr(f"""
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-md w-full">
                <div class="uk-card-body text-center">
                    <h1 class="uk-card-title text-3xl font-bold justify-center mb-2">Reset Password</h1>
                    <p class="text-muted-foreground mb-6">
                        Enter your email and we'll send you a link to reset your password.
                    </p>

                    {error_html}

                    <form action="/forgot-password" method="POST" class="space-y-4">
                        <div class="space-y-2">
                            <input
                                type="email"
                                name="email"
                                placeholder="your.email@example.com"
                                class="uk-input w-full"
                                required
                                autofocus
                            />
                        </div>

                        <button type="submit" class="uk-btn uk-btn-primary w-full">
                            Send Reset Link
                        </button>
                    </form>

                    <div class="border-t border-border my-4 text-muted-foreground text-sm">or</div>

                    <div class="space-y-2">
                        <a href="/reset-password" class="uk-btn uk-btn-secondary uk-btn-sm w-full">
                            I Have a Reset Token
                        </a>
                        <a href="/login" class="hover:underline text-muted-foreground">
                            Back to Login
                        </a>
                    </div>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_reset_password_page(error_message: str | None = None, token: str = "") -> NotStr:
        """
        Render password reset form where user enters token and new password.

        Args:
            error_message: Optional error message to display
            token: Pre-filled token (from URL parameter)

        Returns:
            Password reset form UI as NotStr
        """
        error_html = ""
        if error_message:
            error_html = f"""
            <div class="mb-4 rounded-md bg-red-500/10 border border-red-500/20 p-3 flex items-center gap-2" role="alert">
                <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current shrink-0 h-6 w-6 text-red-400" fill="none" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span class="text-sm text-red-400">{error_message}</span>
            </div>
            """

        return NotStr(f"""
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-md w-full">
                <div class="uk-card-body">
                    <div class="text-center mb-4">
                        <div class="text-5xl mb-2">🔑</div>
                        <h1 class="uk-card-title text-2xl font-bold justify-center">Reset Your Password</h1>
                        <p class="text-muted-foreground text-sm mt-1">
                            Enter your reset token
                        </p>
                    </div>

                    {error_html}

                    <form action="/reset-password/submit" method="POST" class="space-y-4">
                        <div class="space-y-2">
                            <label class="block text-sm font-medium">
                                <span class="block text-sm font-medium">Reset Token</span>
                            </label>
                            <input
                                type="text"
                                name="token"
                                placeholder="Paste your reset token here"
                                class="uk-input w-full font-mono text-sm"
                                value="{token}"
                                required
                            />
                            <label class="block text-sm font-medium">
                                <span class="text-xs text-muted-foreground">
                                    The token from your password reset email
                                </span>
                            </label>
                        </div>

                        <div class="space-y-2">
                            <label class="block text-sm font-medium">
                                <span class="block text-sm font-medium">New Password</span>
                            </label>
                            <input
                                type="password"
                                name="password"
                                placeholder="Enter new password"
                                class="uk-input w-full"
                                minlength="8"
                                required
                            />
                            <label class="block text-sm font-medium">
                                <span class="text-xs text-muted-foreground">
                                    At least 8 characters
                                </span>
                            </label>
                        </div>

                        <div class="space-y-2">
                            <label class="block text-sm font-medium">
                                <span class="block text-sm font-medium">Confirm Password</span>
                            </label>
                            <input
                                type="password"
                                name="confirm_password"
                                placeholder="Confirm new password"
                                class="uk-input w-full"
                                minlength="8"
                                required
                            />
                        </div>

                        <button type="submit" class="uk-btn uk-btn-primary w-full">
                            Reset Password
                        </button>
                    </form>

                    <div class="border-t border-border my-4 text-muted-foreground text-sm">or</div>

                    <div class="text-center">
                        <a href="/login" class="hover:underline text-muted-foreground">
                            Back to Login
                        </a>
                    </div>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_reset_password_success() -> NotStr:
        """
        Render password reset success page.

        Returns:
            Password reset success UI as NotStr
        """
        return NotStr("""
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-md w-full">
                <div class="uk-card-body text-center">
                    <div class="text-6xl mb-4">✅</div>
                    <h1 class="uk-card-title text-3xl font-bold justify-center mb-2">Password Reset!</h1>
                    <p class="text-muted-foreground mb-6">
                        Your password has been reset successfully.
                        You can now log in with your new password.
                    </p>

                    <a href="/login" class="uk-btn uk-btn-primary w-full">
                        Go to Login
                    </a>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_email_verification_sent(email: str) -> NotStr:
        """
        Render email verification sent page.

        Args:
            email: The email address verification was sent to

        Returns:
            Email verification sent UI as NotStr
        """
        return NotStr(f"""
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-lg w-full">
                <div class="uk-card-body text-center">
                    <div class="text-6xl mb-4">✉️</div>
                    <h1 class="uk-card-title text-3xl font-bold justify-center mb-2">Check Your Email</h1>
                    <p class="text-lg text-muted-foreground mb-4">
                        We've sent a verification email to <strong>{email}</strong>.
                    </p>
                    <p class="text-foreground/80 mb-6">
                        Please click the link in the email to verify your account before logging in.
                    </p>

                    <div class="uk-card-footer justify-center">
                        <a href="/login" class="uk-btn uk-btn-primary w-full">Go to Login</a>
                    </div>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_password_reset_sent(email: str) -> NotStr:
        """
        Render password reset email sent page.

        Args:
            email: The email address reset instructions were sent to

        Returns:
            Password reset sent UI as NotStr
        """
        return NotStr(f"""
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-md w-full">
                <div class="uk-card-body text-center">
                    <h1 class="uk-card-title text-3xl font-bold justify-center mb-4">Check Your Email</h1>
                    <p class="text-muted-foreground mb-6">
                        If an account exists for <strong>{email}</strong>, you'll receive password reset instructions shortly.
                    </p>

                    <div class="uk-card-footer justify-center">
                        <a href="/login" class="uk-btn uk-btn-primary w-full">Back to Login</a>
                    </div>
                </div>
            </div>
        </div>
        """)

    @staticmethod
    def render_email_verified() -> NotStr:
        """
        Render email verified callback page.

        Returns:
            Email verified UI with meta-refresh redirect as NotStr
        """
        return NotStr("""
        <meta http-equiv="refresh" content="2;url=/login">
        <div class="min-h-screen bg-muted flex items-center justify-center p-6">
            <div class="uk-card uk-card-default bg-background shadow-xl max-w-lg w-full">
                <div class="uk-card-body text-center">
                    <div class="text-6xl mb-4">✅</div>
                    <h1 class="uk-card-title text-3xl font-bold justify-center mb-2">Email Verified!</h1>
                    <p class="text-lg text-muted-foreground mb-4">
                        Your email has been verified successfully.
                    </p>
                    <p class="text-foreground/80 mb-6">
                        <span class="uk-spinner uk-spinner-small"></span>
                        Redirecting you to login...
                    </p>
                </div>
            </div>
        </div>
        """)


__all__ = ["AuthComponents"]
