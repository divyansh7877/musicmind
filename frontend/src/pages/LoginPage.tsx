import { SignIn } from '@clerk/react';

export default function LoginPage() {
  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center px-6">
      <SignIn
        routing="path"
        path="/login"
        signUpUrl="/register"
        fallbackRedirectUrl="/"
        forceRedirectUrl="/"
      />
    </div>
  );
}
