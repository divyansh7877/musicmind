import { RedirectToSignIn, SignIn } from '@clerk/react';
import { useEffect } from 'react';

export default function LoginPage() {
  return (
    <div className="min-h-[calc(100vh-10rem)] flex items-center justify-center px-6">
      <SignIn
        routing="path"
        path="/login"
        signUpUrl="/register"
        afterSignInUrl="/"
        fallback={<RedirectToSignIn />}
      />
    </div>
  );
}
