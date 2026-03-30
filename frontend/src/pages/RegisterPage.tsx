import { RedirectToSignUp, SignUp } from '@clerk/react';

export default function RegisterPage() {
  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center px-6">
      <SignUp
        routing="path"
        path="/register"
        signInUrl="/login"
        afterSignUpUrl="/"
      />
    </div>
  );
}
